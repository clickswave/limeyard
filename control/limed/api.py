#!/usr/bin/env python3
"""limed HTTP API - what the SvelteKit UI and the scan harness talk to.

Stdlib only, on purpose: the control image is alpine + python3 + py3-yaml with
no pip, and a local control plane does not need a web framework.

Everything here is read-mostly except the lifecycle POSTs, which shell out to
`docker compose` exactly as the CLI does. Bind loopback only.
"""
import json
import os
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


def target_view(t, with_truth=False):
    label, _ = lime.state_of(t)
    up = t.get("upstream") or {}
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
        "egress": bool(t.get("egress")),
        "disk": t.get("disk"),
        "setup": t.get("setup"),
        "credentials": t.get("credentials") or [],
        "session_cookies": t.get("session_cookies") or {},
        "ports": [{"port": p, "service": s} for p, s, _ in lime.host_ports(t)],
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
    if with_truth:
        v["truth"] = lime.load_truth(t)
    return v


def scenario_view(s):
    label, _ = lime.state_of(s)
    return {
        "slug": s["slug"],
        "name": s.get("name"),
        "description": s.get("description"),
        "state": label,
        "hosts": s.get("hosts") or [],
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
        import hmac
        return hmac.compare_digest(sent, TOKEN)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
                "/api/targets", "/api/targets/<slug>", "/api/scenarios",
                "/api/status", "/api/ports", "/api/doctor", "/api/truth",
                "/api/credits", "/api/score (POST)", "/api/events (SSE)",
                "/api/targets/<slug>/logs (SSE)"]})

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
            return self._send(200, target_view(t, with_truth=True))

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
            seen, off_loopback = {}, []
            for t in ts.values():
                for hp, svc, ip in lime.host_ports(t):
                    seen.setdefault(hp, []).append(f"{t['slug']}/{svc}")
                    if ip and ip not in ("127.0.0.1", "localhost"):
                        off_loopback.append({"target": t["slug"], "service": svc,
                                             "bind": f"{ip}:{hp}"})
            return self._send(200, {
                "ports": [{"port": k, "owners": v, "clash": len(v) > 1}
                          for k, v in sorted(seen.items(),
                                             key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)],
                "off_loopback": off_loopback,
            })

        if p == "/api/credits":
            ts = lime.load_targets()
            return self._send(200, {"credits": [
                {"slug": t["slug"], "name": t.get("name"), "kind": t.get("kind"),
                 **target_view(t)["upstream"]}
                for t in sorted(ts.values(), key=lambda x: (x.get("kind", ""), x["slug"]))]})

        if p == "/api/doctor":
            return self._send(200, self._doctor())

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
            d = os.path.join(lime.TRUTH_DIR, "scorecards")
            cards = []
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d), reverse=True):
                    if not fn.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(d, fn)) as f:
                            c = json.load(f)
                        cards.append({"file": fn, "tool": c.get("tool"),
                                      "generated": c.get("generated"),
                                      "totals": c.get("totals"),
                                      "by_class": c.get("by_class"),
                                      "by_target": c.get("by_target")})
                    except Exception:
                        continue
            return self._send(200, {"scorecards": cards})

        if p == "/api/events":
            return self._stream_events()

        return self._send(404, {"error": "not found", "path": p})

    def _doctor(self):
        checks, ok = [], True
        dok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
        checks.append({"check": "docker", "ok": dok})
        ok &= dok
        for t in lime.load_targets().values():
            up = t.get("upstream") or {}
            if not up.get("author"):
                checks.append({"check": "attribution", "target": t["slug"], "ok": False,
                               "detail": "target.yml has no upstream.author"})
                ok = False
            if not up.get("license"):
                checks.append({"check": "license", "target": t["slug"], "ok": False,
                               "detail": "upstream.license missing"})
        pct, gb = lime._disk_free_pct()
        checks.append({"check": "disk", "ok": bool(pct and pct >= 5),
                       "detail": f"{pct:.1f}% free ({gb:.0f} GB)" if pct else "unknown"})
        return {"ok": ok, "checks": checks}

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
        """State transitions, polled. Cheap and good enough for a local lab."""
        self._sse_open()
        last = {}
        try:
            while True:
                ts = lime.load_targets()
                for slug, t in ts.items():
                    label, _ = lime.state_of(t)
                    if last.get(slug) != label:
                        if slug in last:
                            self._sse("state", {"slug": slug, "from": last[slug], "to": label})
                        last[slug] = label
                self._sse("tick", {"time": time.time(), "states": last})
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

        if p.startswith("/api/targets/"):
            slug, _, action = p[len("/api/targets/"):].partition("/")
            ts = lime.load_targets()
            if slug not in ts:
                return self._send(404, {"error": f"unknown target '{slug}'"})
            t = ts[slug]
            if action not in ("start", "stop", "restart", "pull", "setup"):
                return self._send(400, {"error": f"unknown action '{action}'"})

            # Disk guard. A lab that fills the host disk takes the dev box with
            # it, so heavy targets are refused rather than merely warned about.
            pct, _ = lime._disk_free_pct()
            if action in ("start", "restart", "pull") and lime.is_heavy(t) \
                    and pct is not None and pct < 5:
                return self._send(507, {
                    "error": "refusing to start a heavy target below 5% free disk",
                    "free_pct": round(pct, 1),
                    "hint": "docker builder prune"})

            threading.Thread(target=self._run_action, args=(t, action), daemon=True).start()
            return self._send(202, {"target": slug, "action": action, "accepted": True})

        if p.startswith("/api/scenarios/"):
            slug, _, action = p[len("/api/scenarios/"):].partition("/")
            sc = lime.load_scenarios()
            if slug not in sc:
                return self._send(404, {"error": f"unknown scenario '{slug}'"})
            if action not in ("up", "down"):
                return self._send(400, {"error": f"unknown action '{action}'"})
            s = sc[slug]
            threading.Thread(
                target=lambda: (lime.ensure_networks(), lime.dc(s, "up", "-d"), lime.run_setup(s))
                if action == "up" else lime.dc(s, "down"), daemon=True).start()
            return self._send(202, {"scenario": slug, "action": action, "accepted": True})

        return self._send(404, {"error": "not found", "path": p})

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
