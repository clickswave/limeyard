#!/usr/bin/env python3
"""limed HTTP API - what the SvelteKit UI and the scan harness talk to.

Stdlib only, on purpose: the control image is alpine + python3 + py3-yaml with
no pip, and a local control plane does not need a web framework.

Everything here is read-mostly except the lifecycle POSTs, which shell out to
`docker compose` exactly as the CLI does. Bind loopback only.
"""
import hmac
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import lime
import scorer

BIND = os.environ.get("LIMED_BIND", "0.0.0.0")

# limed holds the Docker socket, which is root-equivalent on the host, and it
# has to sit on the same network as the targets so setup hooks can curl them.
# Docker bridges are bidirectional, so "limed can reach targets but targets
# cannot reach limed" is not expressible in compose. A shared secret is: a
# target that gets popped can open a socket to limed and learn nothing.
TOKEN = os.environ.get("LIME_TOKEN", "").strip()
OPEN_PATHS = {"/api/health"}

TARGET_ACTIONS = ("start", "stop", "restart", "pull", "setup")
SCENARIO_ACTIONS = ("up", "down", "restart")
STALE_DAYS = 180


# ------------------------------------------------------------------ views ---
def target_view(t, full=False):
    label, _ = lime.state_of(t)
    up = t.get("upstream") or {}
    services = lime.compose_services(t)
    v = {
        "slug": t["slug"],
        "name": t.get("name"),
        "kind": t.get("kind"),
        "description": t.get("description"),
        "stack": t.get("stack"),
        "url": t.get("url"),
        "web_seed": t.get("web_seed"),
        "state": label,
        "heavy": lime.is_heavy(t),
        "fixture": lime.is_fixture(t),
        "egress": bool(t.get("egress")),
        "disk": t.get("disk"),
        "setup": t.get("setup"),
        "credentials": t.get("credentials") or [],
        "session_cookies": t.get("session_cookies") or {},
        "ports": [{"port": p, "service": s} for p, s, _ in lime.host_ports(t)],
        "lab_ips": [s["lab_ip"] for s in services if s["lab_ip"]],
        # Attribution travels with every representation of a target. The UI is
        # required to render it; nothing here is optional or lazily loaded.
        "upstream": {
            "author": up.get("author"),
            "packager": up.get("packager"),
            "repo": up.get("repo"),
            "homepage": up.get("homepage"),
            "license": up.get("license") or "unknown",
            "verified": str(up.get("verified") or ""),
            "note": up.get("note"),
        },
        "has_truth": os.path.exists(t["truth_path"]),
        "fetched": lime.fetched(t),
        "compose_present": not lime.missing(t),
    }
    if full:
        v["truth"] = lime.load_truth(t)
        v["images"] = [{"service": s["service"], "image": s["image"], "pinned": s["pinned"]}
                       for s in services if s["image"]]
        v["artifact"] = t.get("artifact")
    return v


def scenario_view(s):
    label, _ = lime.state_of(s)
    return {
        "slug": s["slug"],
        "name": s.get("name"),
        "description": s.get("description"),
        "state": label,
        "resolver": s.get("resolver"),
        "resolver_host": s.get("resolver_host"),
        "subnet": lime.LAB_SUBNET,
        "hosts": s.get("hosts") or [],
        "host_states": lime.host_states(s),
        "zones": s.get("zones") or [],
        "expected_assets": s.get("expected_assets") or {},
        "upstream": s.get("upstream") or {"author": "Clickswave"},
    }


def _counts(targets):
    by_state, by_kind = {}, {}
    for t in targets.values():
        label, _ = lime.state_of(t)
        key = label.split()[0]
        by_state[key] = by_state.get(key, 0) + 1
        by_kind[t.get("kind", "?")] = by_kind.get(t.get("kind", "?"), 0) + 1
    return by_state, by_kind


def _card_summary(card, fn):
    """What the history list carries per run. by_class gains a false-positive
    count derived from by_target, so cards saved before that was tracked still
    show it."""
    by_class = {k: dict(v) for k, v in (card.get("by_class") or {}).items()}
    for r in (card.get("by_target") or {}).values():
        for fp in r.get("false_positives") or []:
            c = fp.get("class") or "?"
            by_class.setdefault(c, {"expected": 0, "detected": 0, "recall": None})
            by_class[c]["false_positive"] = by_class[c].get("false_positive", 0) + 1
    for v in by_class.values():
        v.setdefault("false_positive", 0)
    return {"id": fn[:-5] if fn.endswith(".json") else fn,
            "file": fn,
            "tool": card.get("tool"),
            "generated": card.get("generated"),
            "totals": card.get("totals"),
            "by_class": by_class,
            "by_target": card.get("by_target")}


def _scorecards():
    d = os.path.join(lime.TRUTH_DIR, "scorecards")
    cards = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d), reverse=True):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fn)) as f:
                    cards.append(_card_summary(json.load(f), fn))
            except Exception:
                continue
    # Newest first by the timestamp inside the card, not the filename, so a
    # relabelled run sorts by when it happened.
    cards.sort(key=lambda c: c.get("generated") or "", reverse=True)
    return cards


# ----------------------------------------------------------------- doctor ---
def _check(cid, name, verdict, reason, value=None, items=None):
    return {"id": cid, "name": name, "verdict": verdict, "reason": reason,
            "value": value, "items": items or []}


def doctor(targets):
    """Environment, attribution, supply chain and hardening, as one list of
    checks with a verdict each. The CLI's doctor and audit print the same
    facts; this is the shape the panel renders."""
    checks = []
    ts = list(targets.values())
    n = len(ts)

    r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                       capture_output=True, text=True)
    dok = r.returncode == 0
    ver = r.stdout.strip() if dok else None
    checks.append(_check("docker", "Docker daemon reachable",
                         "pass" if dok else "fail",
                         f"Engine {ver} answering on the socket." if dok
                         else "docker version failed. Is the socket mounted and the daemon up?",
                         ver))

    r = subprocess.run(["docker", "compose", "version", "--short"],
                       capture_output=True, text=True)
    cok = r.returncode == 0
    checks.append(_check("compose-plugin", "Compose plugin present",
                         "pass" if cok else "fail",
                         f"compose {r.stdout.strip()} available as a docker subcommand." if cok
                         else "docker compose is not installed; nothing can start.",
                         r.stdout.strip() if cok else None))

    for net, what in ((lime.WEB_NET, "web"), (lime.LAB_NET, "lab")):
        nok = subprocess.run(["docker", "network", "inspect", net],
                             capture_output=True).returncode == 0
        extra = f" Subnet {lime.LAB_SUBNET}." if what == "lab" else ""
        checks.append(_check(f"net-{what}", f"Network {net} present",
                             "pass" if nok else "warn",
                             (f"Bridge exists.{extra}" if nok
                              else "Absent. It is created on the first start, so this is fine "
                                   "until something needs it."),
                             lime.LAB_SUBNET if what == "lab" else "bridge"))

    tok = bool(os.environ.get("LIME_TOKEN", "").strip())
    checks.append(_check("token", "API token set",
                         "pass" if tok else "fail",
                         "Every limed call needs X-Lime-Token." if tok
                         else "LIME_TOKEN is unset. limed holds the Docker socket and shares a "
                              "network with the targets; any popped target can drive it.",
                         "required" if tok else "unset"))

    pct, gb = lime._disk_free_pct()
    if pct is None:
        checks.append(_check("disk", "Disk headroom", "warn", "Could not measure free space.", None))
    else:
        v = "fail" if pct < 5 else ("warn" if pct < 12 else "pass")
        reason = {"fail": "Below 5% free. Heavy targets are refused until space is reclaimed "
                          "(docker builder prune).",
                  "warn": "Under 12% free. Heavy targets still start, but not many of them.",
                  "pass": "Enough for the heavy targets."}[v]
        checks.append(_check("disk", "Disk headroom", v, reason, f"{gb:.0f} GB free ({pct:.0f}%)"))

    missing_author = [t["slug"] for t in ts if not (t.get("upstream") or {}).get("author")]
    checks.append(_check("attribution", "Attribution complete",
                         "fail" if missing_author else "pass",
                         "Every target names its author." if not missing_author
                         else "Targets without upstream.author. The manager refuses to register one.",
                         f"{n - len(missing_author)} / {n}", missing_author))

    missing_lic = [t["slug"] for t in ts if not (t.get("upstream") or {}).get("license")]
    checks.append(_check("licence", "Licences declared",
                         "warn" if missing_lic else "pass",
                         "Every target records a licence, or the literal 'none declared'."
                         if not missing_lic else "Targets with no upstream.license recorded.",
                         f"{n - len(missing_lic)} / {n}", missing_lic))

    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - STALE_DAYS * 86400))
    stale = []
    for t in ts:
        v = str((t.get("upstream") or {}).get("verified") or "")[:10]
        if not v or v < cutoff:
            stale.append(f"{t['slug']} ({v or 'never'})")
    checks.append(_check("fresh", "Upstream verification fresh",
                         "warn" if stale else "pass",
                         f"Every target was checked within {STALE_DAYS} days." if not stale
                         else f"Last verified more than {STALE_DAYS} days ago, or never. "
                              "A build waiting to fail.",
                         f"{n - len(stale)} / {n}", stale))

    no_truth = [t["slug"] for t in ts if not os.path.exists(t["truth_path"])]
    checks.append(_check("truth", "Answer keys present",
                         "warn" if no_truth else "pass",
                         "Every target ships a truth.yml." if not no_truth
                         else "Targets without truth.yml cannot be scored.",
                         f"{n - len(no_truth)} / {n}", no_truth))

    absent, unfetched = [], []
    for t in ts:
        if lime.is_fixture(t) or not lime.missing(t):
            continue
        (unfetched if t.get("repo") else absent).append(t["slug"])
    runnable = [t for t in ts if not lime.is_fixture(t)]
    checks.append(_check("compose", "Compose files present",
                         "fail" if absent else ("warn" if unfetched else "pass"),
                         "Every runnable target has its compose file." if not (absent or unfetched)
                         else ("Compose missing for targets that vendor nothing. " if absent else "")
                         + ("Source not fetched yet; it is cloned on first start." if unfetched else ""),
                         f"{len(runnable) - len(absent) - len(unfetched)} / {len(runnable)}",
                         absent + [f"{s} (not fetched)" for s in unfetched]))

    # Supply chain and hardening come from the same invariants `lime audit` enforces.
    paths = [t["compose_path"] for t in runnable] + \
            [s["compose_path"] for s in lime.load_scenarios().values()]
    hard_fail, unpinned, warn_other = [], [], []
    for path, doc, err in lime._compose_docs(paths):
        if err:
            hard_fail.append(f"{os.path.relpath(path, lime.BASE)}: unparseable ({err})")
            continue
        for level, msg in lime.audit_compose(path, doc):
            if level == "fail":
                hard_fail.append(msg)
            elif "not pinned by digest" in msg:
                # "path::service: image is not pinned by digest" -> "image (path)"
                where_, _, rest = msg.partition(": ")
                unpinned.append(f"{rest.replace(' is not pinned by digest', '')} in {where_}")
            else:
                warn_other.append(msg)
    total_images = sum(1 for t in runnable for s in lime.compose_services(t) if s["image"])
    checks.append(_check("pinned", "Images pinned to digest",
                         "warn" if unpinned else "pass",
                         "Every image references the digest that was pulled and tested here."
                         if not unpinned else
                         "Floating tags. Pin images rewrites the lab's own compose files; an "
                         "image inside a fetched source tree (targets/*/*/src) has to be pinned "
                         "upstream, or it comes back on the next clone.",
                         f"{max(total_images - len(unpinned), 0)} / {total_images}", unpinned))
    checks.append(_check("hardening", "Containers hardened",
                         "fail" if hard_fail else ("warn" if warn_other else "pass"),
                         "cap_drop ALL, no-new-privileges, pid and memory limits, loopback binds."
                         if not (hard_fail or warn_other)
                         else "Invariants that keep RCE inside the container are not met.",
                         f"{len(hard_fail)} failing" if hard_fail else
                         (f"{len(warn_other)} warnings" if warn_other else "all"),
                         hard_fail + warn_other))

    off, seen = [], {}
    for t in ts:
        for hp, svc, ip in lime.host_ports(t):
            seen.setdefault(hp, []).append(f"{t['slug']}/{svc}")
            if ip and ip not in ("127.0.0.1", "localhost"):
                off.append(f"{t['slug']}/{svc} on {ip or '0.0.0.0'}:{hp}")
    checks.append(_check("loopback", "No target binds off loopback",
                         "fail" if off else "pass",
                         "Every published port binds to 127.0.0.1." if not off
                         else "Reachable from other machines. This lab must never be.",
                         f"{len(off)} exposed" if off else "all", off))
    clashes = [f"{k}: {', '.join(v)}" for k, v in seen.items() if len(v) > 1]
    checks.append(_check("clash", "Host ports unique",
                         "fail" if clashes else "pass",
                         "No two targets publish the same port." if not clashes
                         else "Two targets claim one port; the second to start loses.",
                         f"{len(seen)} ports", clashes))

    for c in checks:
        f = FIXES.get(c["id"])
        c["fix"] = {"label": f[0], "description": f[1]} if f else None
    summary = {k: sum(1 for c in checks if c["verdict"] == k) for k in ("pass", "warn", "fail")}
    fixable = [c["id"] for c in checks if c["fix"] and c["verdict"] != "pass"]
    return {"ok": summary["fail"] == 0, "summary": summary, "checks": checks,
            "fixable": fixable, "generated": time.time()}


# ------------------------------------------------------------------ fixes ---
# One click repairs. Each fixer takes the targets map and returns a message.
# Only problems with an unambiguous, reversible-by-git remedy get one:
# attribution, licences, port clashes and hardening need a person to decide.

_PORT_SHORT = re.compile(r"^(\s*-\s*['\"]?)(?:0\.0\.0\.0:)?(\d+:\d+(?:/\w+)?)(['\"]?\s*)$")
_PORT_HOST_IP = re.compile(r"^(\s*host_ip:\s*['\"]?)(?:0\.0\.0\.0|::)(['\"]?\s*)$")
_VERIFIED = re.compile(r"^(\s*verified:\s*).*$")


class FixIncomplete(Exception):
    """A fixer did what it could and the check will still not pass."""


def _fix_networks(targets):
    lime.ensure_networks()
    return f"created {lime.WEB_NET} and {lime.LAB_NET} where they were missing"


def _fix_disk(targets):
    before = lime._disk_free_pct()[1] or 0
    for cmd in (["docker", "builder", "prune", "-f"], ["docker", "image", "prune", "-f"]):
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    after = lime._disk_free_pct()[1] or 0
    return f"pruned build cache and dangling images, reclaimed {max(after - before, 0):.1f} GB"


def _fix_pinned(targets):
    import pin
    os.environ.setdefault("LIMEYARD_DIR", lime.BASE)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pin.run(True)
    tail = [l for l in buf.getvalue().splitlines() if l.strip()]
    summary = tail[-1] if tail else "nothing to pin"
    unresolved = [l.strip() for l in tail if l.strip().startswith("unresolved")]
    if rc:
        raise FixIncomplete(summary + "; could not resolve "
                            + ", ".join(u.split()[-1] for u in unresolved))
    # Whatever is still floating now lives in a fetched source tree, which this
    # fixer must not touch: the next clone would undo it. Say so, and fail.
    left = [c for c in doctor(targets)["checks"] if c["id"] == "pinned"][0]
    if left["verdict"] != "pass":
        raise FixIncomplete(summary + ". Still floating, inside fetched source: "
                            + "; ".join(left["items"]) + ". Pin those upstream.")
    return summary


def _fix_sources(targets):
    done, failed = [], []
    for t in targets.values():
        if lime.is_fixture(t) or not lime.missing(t) or not t.get("repo"):
            continue
        (done if lime.ensure_src(t) else failed).append(t["slug"])
    if not done and not failed:
        return "nothing to fetch"
    msg = f"fetched {', '.join(done)}" if done else ""
    if failed:
        msg += ("; " if msg else "") + f"clone failed for {', '.join(failed)}"
    return msg


def _fix_fresh(targets):
    """Stamp today on stale targets that are running right now. That is a
    real verification: the image pulled, the container came up. Stopped ones
    stay stale until someone starts them and sees them work."""
    today = time.strftime("%Y-%m-%d")
    cutoff = time.strftime("%Y-%m-%d", time.localtime(time.time() - STALE_DAYS * 86400))
    stamped, skipped = [], []
    for t in targets.values():
        v = str((t.get("upstream") or {}).get("verified") or "")[:10]
        if v and v >= cutoff:
            continue
        if lime.state_of(t)[0] != "running":
            skipped.append(t["slug"])
            continue
        path = os.path.join(t["dir"], "target.yml")
        try:
            lines = open(path).read().splitlines(keepends=True)
        except OSError:
            skipped.append(t["slug"])
            continue
        out, hit = [], False
        for line in lines:
            m = _VERIFIED.match(line.rstrip("\n"))
            if m and not hit:
                out.append(f"{m.group(1)}{today}\n")
                hit = True
            else:
                out.append(line)
        if not hit:
            # No verified line at all: add one under upstream.
            out2, added = [], False
            for line in out:
                out2.append(line)
                if not added and line.strip().startswith("upstream:"):
                    out2.append(f"  verified: {today}\n")
                    added = True
            out, hit = out2, added
        if hit:
            open(path, "w").writelines(out)
            stamped.append(t["slug"])
        else:
            skipped.append(t["slug"])
    msg = f"stamped {today} on {', '.join(stamped)}" if stamped else "nothing running to verify"
    if skipped:
        msg += f"; not running, left stale: {', '.join(skipped)}"
    return msg


def _fix_loopback(targets):
    changed = []
    for t in targets.values():
        if lime.is_fixture(t) or lime.missing(t):
            continue
        if not any(ip and ip not in ("127.0.0.1", "localhost") for _, _, ip in lime.host_ports(t)):
            continue
        path = t["compose_path"]
        out, hit = [], False
        for line in open(path).read().splitlines(keepends=True):
            body = line.rstrip("\n")
            m = _PORT_SHORT.match(body)
            if m:
                out.append(f"{m.group(1)}127.0.0.1:{m.group(2)}{m.group(3)}\n")
                hit = True
                continue
            m = _PORT_HOST_IP.match(body)
            if m:
                out.append(f"{m.group(1)}127.0.0.1{m.group(2)}\n")
                hit = True
                continue
            out.append(line)
        if hit:
            open(path, "w").writelines(out)
            changed.append(t["slug"])
    if not changed:
        return "nothing bound off loopback"
    return f"rewrote port binds to 127.0.0.1 in {', '.join(changed)}; restart them to apply"


FIXES = {
    "net-web": ("Create networks", "Runs the same network create the first start would.", _fix_networks),
    "net-lab": ("Create networks", "Runs the same network create the first start would.", _fix_networks),
    "disk": ("Reclaim space", "docker builder prune and docker image prune, dangling only. "
             "Nothing a running target uses is touched.", _fix_disk),
    "pinned": ("Pin images", "Rewrites every floating tag in the lab's compose files to the "
               "digest pulled here, the same as lime pin --apply. Fetched source trees are "
               "left alone.", _fix_pinned),
    "compose": ("Fetch sources", "git clone the repo-backed targets that have not been fetched.",
                _fix_sources),
    "fresh": ("Re-verify running", "Stamps today on stale targets that are up right now. "
              "Stopped ones stay stale until they are started and seen to work.", _fix_fresh),
    "loopback": ("Bind to loopback", "Rewrites 0.0.0.0 and bare port binds to 127.0.0.1 in the "
                 "compose file. Takes effect on restart.", _fix_loopback),
}


def fix(ids=None):
    """Run the fixers for the given check ids, or every fixable failing
    check. Returns per-fix results and a fresh doctor report."""
    targets = lime.load_targets()
    report = doctor(targets)
    wanted = ids if ids else report["fixable"]
    results, ran = [], set()
    for cid in wanted:
        f = FIXES.get(cid)
        if not f:
            results.append({"id": cid, "ok": False, "message": "no automatic fix for this check"})
            continue
        if f[2] in ran:
            continue  # both network checks share one fixer
        ran.add(f[2])
        try:
            results.append({"id": cid, "ok": True, "message": f[2](targets)})
        except FixIncomplete as e:
            results.append({"id": cid, "ok": False, "message": str(e)})
        except Exception as e:
            results.append({"id": cid, "ok": False, "message": f"{type(e).__name__}: {e}"})
    return {"results": results, "doctor": doctor(lime.load_targets())}


# --------------------------------------------------------------- handler ---
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "limed"

    def log_message(self, fmt, *a):  # quieter than the default
        if os.environ.get("LIMED_ACCESS_LOG"):
            super().log_message(fmt, *a)

    # ------------------------------------------------------------- helpers ---
    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _sse_open(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _sse(self, event, data):
        self.wfile.write(f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode())
        self.wfile.flush()

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def _authed(self, path):
        if not TOKEN or path in OPEN_PATHS:
            return True
        sent = self.headers.get("X-Lime-Token", "")
        # constant-time compare; the token is short and an attacker on the lab
        # network could otherwise time their way to it.
        return hmac.compare_digest(sent, TOKEN)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Lime-Token")
        self.end_headers()

    # ----------------------------------------------------------------- GET ---
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/") or "/"
        q = parse_qs(u.query)
        try:
            return self._get(p, q)
        except BrokenPipeError:
            return
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _get(self, p, q):
        if p == "/api/health":
            return self._send(200, {"ok": True, "auth": bool(TOKEN)})
        if not self._authed(p):
            return self._send(401, {"error": "missing or bad X-Lime-Token"})
        if p in ("/", "/api"):
            return self._send(200, {"service": "limed", "endpoints": [
                "/api/targets", "/api/targets/<slug>", "/api/targets/<slug>/logs (SSE)",
                "/api/targets/<slug>/<start|stop|restart|pull|setup> (POST)",
                "/api/targets/bulk (POST {action, slugs})",
                "/api/scenarios", "/api/scenarios/<slug>",
                "/api/scenarios/<slug>/<up|down|restart> (POST)",
                "/api/status", "/api/ports", "/api/doctor", "/api/doctor/fix (POST {ids})",
                "/api/truth", "/api/credits",
                "/api/scorecards", "/api/scorecards/<id>", "/api/score (POST)",
                "/api/events (SSE)"]})

        if p == "/api/targets":
            ts = lime.load_targets()
            kind = (q.get("kind") or [None])[0]
            out = [target_view(t) for t in ts.values() if not kind or t.get("kind") == kind]
            return self._send(200, {"targets": out, "kinds": lime.KINDS})

        if p.startswith("/api/targets/"):
            rest = p[len("/api/targets/"):]
            slug, _, tail = rest.partition("/")
            ts = lime.load_targets()
            if slug not in ts:
                return self._send(404, {"error": f"unknown target '{slug}'"})
            t = ts[slug]
            if tail == "logs":
                return self._stream_logs(t)
            if tail == "truth":
                return self._send(200, lime.load_truth(t) or {})
            return self._send(200, target_view(t, full=True))

        if p == "/api/scenarios":
            return self._send(200, {"scenarios": [scenario_view(s)
                                                  for s in lime.load_scenarios().values()]})

        if p.startswith("/api/scenarios/"):
            slug = p[len("/api/scenarios/"):].split("/")[0]
            sc = lime.load_scenarios()
            if slug not in sc:
                return self._send(404, {"error": f"unknown scenario '{slug}'"})
            return self._send(200, scenario_view(sc[slug]))

        if p == "/api/status":
            ts = lime.load_targets()
            by_state, by_kind = _counts(ts)
            pct, gb = lime._disk_free_pct()
            return self._send(200, {
                "targets": len(ts),
                "by_state": by_state,
                "by_kind": by_kind,
                "scenarios": len(lime.load_scenarios()),
                "disk": {"free_pct": round(pct, 1) if pct else None,
                         "free_gb": round(gb, 1) if gb else None,
                         "heavy_blocked": bool(pct is not None and pct < 5)},
                "networks": {"web": lime.WEB_NET, "lab": lime.LAB_NET,
                             "lab_subnet": lime.LAB_SUBNET},
                "time": time.time(),
            })

        if p == "/api/ports":
            ts = lime.load_targets()
            seen, off_loopback, lab = {}, [], []
            for t in ts.values():
                for hp, svc, ip in lime.host_ports(t):
                    seen.setdefault(hp, []).append({"slug": t["slug"], "name": t.get("name"),
                                                    "kind": t.get("kind"), "service": svc})
                    if ip and ip not in ("127.0.0.1", "localhost"):
                        off_loopback.append({"target": t["slug"], "service": svc,
                                             "bind": f"{ip}:{hp}"})
                for s in lime.compose_services(t):
                    if s["lab_ip"]:
                        lab.append({"ip": s["lab_ip"], "names": [], "ports": [],
                                    "owner": t["slug"], "owner_name": t.get("name"),
                                    "service": s["service"], "via": "target"})
            for s in lime.load_scenarios().values():
                for h in s.get("hosts") or []:
                    lab.append({"ip": h.get("ip"), "names": h.get("names") or [],
                                "ports": h.get("ports") or [], "owner": s["slug"],
                                "owner_name": s.get("name"), "note": h.get("note"),
                                "via": "scenario"})
            lab.sort(key=lambda h: [int(x) for x in str(h["ip"]).split(".")]
                     if str(h["ip"]).count(".") == 3 and all(x.isdigit() for x in str(h["ip"]).split("."))
                     else [0])
            return self._send(200, {
                "ports": [{"port": k, "owners": v, "clash": len(v) > 1}
                          for k, v in sorted(seen.items(),
                                             key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)],
                "off_loopback": off_loopback,
                "lab": lab,
                "subnet": lime.LAB_SUBNET,
            })

        if p == "/api/credits":
            ts = lime.load_targets()
            return self._send(200, {"credits": [
                {"slug": t["slug"], "name": t.get("name"), "kind": t.get("kind"),
                 **target_view(t)["upstream"]}
                for t in sorted(ts.values(), key=lambda x: (x.get("kind", ""), x["slug"]))]})

        if p == "/api/doctor":
            return self._send(200, doctor(lime.load_targets()))

        if p == "/api/truth":
            ts = lime.load_targets()
            merged, running_only = {}, (q.get("running") or ["0"])[0] == "1"
            for slug, t in ts.items():
                if running_only and lime.state_of(t)[0] != "running":
                    continue
                tr = lime.load_truth(t)
                if tr:
                    merged[slug] = {**tr, "base_url": t.get("url")}
            return self._send(200, {"targets": merged, "generated": time.time()})

        if p == "/api/scorecards":
            return self._send(200, {"scorecards": _scorecards()})

        if p.startswith("/api/scorecards/"):
            cid = p[len("/api/scorecards/"):]
            if "/" in cid or ".." in cid:
                return self._send(400, {"error": "bad id"})
            path = os.path.join(lime.TRUTH_DIR, "scorecards", cid + ".json")
            if not os.path.exists(path):
                return self._send(404, {"error": f"no scorecard '{cid}'"})
            with open(path) as f:
                return self._send(200, {**_card_summary(json.load(f), cid + ".json")})

        if p == "/api/events":
            return self._stream_events()

        return self._send(404, {"error": "not found", "path": p})

    def _stream_logs(self, t):
        if lime.missing(t):
            return self._send(409, {"error": "compose not present"})
        self._sse_open()
        cmd = ["docker", "compose", "-p", t["project"], "-f", t["compose_path"],
               "logs", "-f", "--tail", "200"]
        proc = subprocess.Popen(cmd, cwd=os.path.dirname(t["compose_path"]),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for line in proc.stdout:
                self._sse("log", {"target": t["slug"], "line": line.rstrip("\n")})
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.terminate()

    def _stream_events(self):
        """State transitions, polled. Cheap and good enough for a local lab.
        Every tick carries the full state map for targets and scenarios, so a
        client that connects late is current after one event."""
        self._sse_open()
        last, last_sc = {}, {}
        try:
            while True:
                for slug, t in lime.load_targets().items():
                    label, _ = lime.state_of(t)
                    if last.get(slug) != label:
                        if slug in last:
                            self._sse("state", {"slug": slug, "from": last[slug], "to": label})
                        last[slug] = label
                for slug, s in lime.load_scenarios().items():
                    label, _ = lime.state_of(s)
                    if last_sc.get(slug) != label:
                        if slug in last_sc:
                            self._sse("scenario", {"slug": slug, "from": last_sc[slug], "to": label})
                        last_sc[slug] = label
                self._sse("tick", {"time": time.time(), "states": last, "scenarios": last_sc})
                time.sleep(int(os.environ.get("LIMED_POLL", "5")))
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---------------------------------------------------------------- POST ---
    def do_POST(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/")
        try:
            return self._post(p)
        except BrokenPipeError:
            return
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _refuse(self, t, action):
        """Why a lifecycle action cannot run, or None."""
        if lime.is_fixture(t):
            return "fixture: nothing to run"
        # Disk guard. A lab that fills the host disk takes the dev box with
        # it, so heavy targets are refused rather than merely warned about.
        if action in ("start", "restart", "pull") and lime.is_heavy(t):
            pct, _ = lime._disk_free_pct()
            if pct is not None and pct < 5:
                return f"refusing to start a heavy target below 5% free disk ({pct:.1f}%)"
        return None

    def _post(self, p):
        if not self._authed(p):
            return self._send(401, {"error": "missing or bad X-Lime-Token"})
        if p == "/api/score":
            body = self._body()
            findings = body.get("findings") or []
            ts = lime.load_targets()
            truth = {}
            for slug, t in ts.items():
                tr = lime.load_truth(t)
                if tr:
                    truth[slug] = tr
            card = scorer.score(findings, truth, tool=body.get("tool", "unknown"),
                                only=body.get("targets"))
            if body.get("save"):
                path = scorer.save(card, lime.TRUTH_DIR)
                card["saved"] = path
            return self._send(200, card)

        if p == "/api/doctor/fix":
            body = self._body()
            ids = body.get("ids") or []
            if not isinstance(ids, list):
                return self._send(400, {"error": "ids must be a list"})
            return self._send(200, fix(ids))

        if p == "/api/targets/bulk":
            body = self._body()
            action = body.get("action")
            slugs = body.get("slugs") or []
            if action not in TARGET_ACTIONS:
                return self._send(400, {"error": f"unknown action '{action}'"})
            ts = lime.load_targets()
            accepted, refused = [], []
            for slug in slugs:
                t = ts.get(slug)
                if not t:
                    refused.append({"slug": slug, "error": "unknown target"})
                    continue
                why = self._refuse(t, action)
                if why:
                    refused.append({"slug": slug, "error": why})
                else:
                    accepted.append(t)
            # A small pool: Docker does not enjoy fourteen simultaneous compose
            # ups, and one at a time would make the panel feel dead.
            threading.Thread(target=self._run_many, args=(accepted, action), daemon=True).start()
            return self._send(202, {"action": action,
                                    "accepted": [t["slug"] for t in accepted],
                                    "refused": refused})

        if p.startswith("/api/targets/"):
            slug, _, action = p[len("/api/targets/"):].partition("/")
            ts = lime.load_targets()
            if slug not in ts:
                return self._send(404, {"error": f"unknown target '{slug}'"})
            t = ts[slug]
            if action not in TARGET_ACTIONS:
                return self._send(400, {"error": f"unknown action '{action}'"})
            why = self._refuse(t, action)
            if why:
                code = 507 if "disk" in why else 409
                return self._send(code, {"error": why, "hint": "docker builder prune"
                                         if code == 507 else None})
            threading.Thread(target=self._run_action, args=(t, action), daemon=True).start()
            return self._send(202, {"target": slug, "action": action, "accepted": True})

        if p.startswith("/api/scenarios/"):
            slug, _, action = p[len("/api/scenarios/"):].partition("/")
            sc = lime.load_scenarios()
            if slug not in sc:
                return self._send(404, {"error": f"unknown scenario '{slug}'"})
            if action not in SCENARIO_ACTIONS:
                return self._send(400, {"error": f"unknown action '{action}'"})
            threading.Thread(target=self._run_scenario, args=(sc[slug], action),
                             daemon=True).start()
            return self._send(202, {"scenario": slug, "action": action, "accepted": True})

        return self._send(404, {"error": "not found", "path": p})

    def _run_many(self, targets, action, width=3):
        queue = list(targets)
        lock = threading.Lock()

        def worker():
            while True:
                with lock:
                    if not queue:
                        return
                    t = queue.pop(0)
                try:
                    self._run_action(t, action)
                except Exception:
                    pass

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(width)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

    def _run_action(self, t, action):
        if action == "setup":
            return lime.run_setup(t)
        if action in ("start", "restart"):
            if action == "restart":
                lime.dc(t, "down")
            lime.ensure_networks()
            if t.get("repo") and not lime.ensure_src(t):
                return
            if lime.missing(t):
                return
            if lime.dc(t, "up", "-d").returncode == 0:
                lime.run_setup(t)
        elif action == "stop":
            lime.dc(t, "down")
        elif action == "pull":
            lime.dc(t, "pull")

    def _run_scenario(self, s, action):
        if action in ("down", "restart"):
            lime.dc(s, "down")
        if action in ("up", "restart"):
            lime.ensure_networks()
            lime.dc(s, "up", "-d")
            lime.run_setup(s)


def serve(port=7099):
    lime.ensure_networks()
    srv = ThreadingHTTPServer((BIND, port), Handler)
    srv.daemon_threads = True
    print(f"limed listening on {BIND}:{port}")
    if TOKEN:
        print("auth: X-Lime-Token required")
    else:
        print("auth: DISABLED (set LIME_TOKEN). Any container on lime-web can "
              "drive this daemon, and it holds the Docker socket.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve(int(os.environ.get("LIMED_PORT", "7099")))
