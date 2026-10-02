#!/usr/bin/env python3
"""mach crawl -> cortex inject, scored end to end.

Every figure measured so far handed cortex the endpoint list out of the
target's own map: 1040 of them on xssmaze, with the parameter names included.
A customer gets whatever the crawl finds, so the honest number is the product
of two things that had only ever been measured separately.

This runs the real path. mach crawls the seed and streams one event per
discovered URL carrying its method, query params and body field names; those
become cortex's injection endpoints with nothing added. The output says both
halves, because a low score has two possible causes and they need different
work: endpoints the crawl never found, and endpoints it found where nothing
was detected.
"""
import json, socket, sys, time
from urllib.parse import urlparse, urlsplit
sys.path.insert(0, "/home/kew/projects/clickswave/projects/limeyard/control/limed")
import yaml, external, scorer

TARGETS = {
    "xssmaze": {"seed": "http://127.0.0.1:7102",
                "dir": "/home/kew/projects/clickswave/projects/limeyard/targets/bench/xssmaze",
                "classes": ["xss", "ssti", "proto_pollution"]},
}
MACH = ("127.0.0.1", int(sys.argv[2]) if len(sys.argv) > 2 else 4441)
CORTEX = ("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 4495)
S = "/tmp/claude-1000/-home-kew-projects-clickswave/913b853d-11fa-42b3-a6bd-6b6c1de6ebb1/scratchpad"
BATCH = 300


def stream(addr, req, timeout=3600):
    s = socket.create_connection(addr, timeout=timeout); s.settimeout(timeout)
    s.sendall((json.dumps(req) + "\n").encode())
    out = []
    for line in s.makefile("rb"):
        line = line.strip()
        if not line: continue
        try: e = json.loads(line)
        except Exception: continue
        out.append(e)
        # Both spellings. mach's stream events use `type` and its dispatcher
        # errors use `status`, and a client that watches one of them hangs on
        # the other.
        if e.get("type") in ("done", "error", "complete") \
                or e.get("status") == "error": break
    s.close(); return out


def crawl(seed, max_pages=4000):
    # `response: "stream"` is not optional: mach only routes `crawl` on the
    # stream path, and without it the request falls through to the request/reply
    # dispatcher, which answers "Unknown operation: crawl" using `status` where
    # the stream protocol uses `type`. A stream client watching `type` sees no
    # terminator and blocks. That cost 32 minutes of a run that looked like a
    # slow crawl and was a client hung on a one-line reply.
    # Params are flat, not nested: DaemonRequest carries them with
    # `#[serde(flatten)]`, the same shape cortex's ops take.
    req = {"operation": "crawl", "response": "stream",
           "seed": seed, "same_host": True, "max_depth": 6,
           "max_pages": max_pages, "tasks": 16, "timeout_ms": 10000,
           "parse_js": True, "capture_static": False, "evasive": True}
    ev = stream(MACH, req)
    seen, eps = set(), []
    for e in ev:
        u = e.get("url")
        if not u or e.get("type") in ("error", "note", "progress", "ack", "done", "complete"):
            continue
        parts = urlsplit(u)
        method = (e.get("method") or "GET").upper()
        q = [p for p in (e.get("params") or []) if isinstance(p, str)]
        b = [p for p in (e.get("body_params") or []) if isinstance(p, str)]
        key = (method, parts.path, tuple(sorted(q)), tuple(sorted(b)))
        if key in seen: continue
        seen.add(key)
        ep = {"method": method, "url": u}
        if b:
            ep["body"] = [{"name": n, "value": "1"} for n in b]
            ep["body_type"] = "form"
        elif q:
            ep["params"] = q
        eps.append(ep)
    return ev, eps


def inject(seed, eps, classes):
    findings, trunc = [], 0
    for i in range(0, len(eps), BATCH):
        req = {"operation": "inject", "response": "stream", "target": seed,
               "timeout_ms": 12000, "tasks": 8, "classes": classes,
               "scope": ["127.0.0.1", "localhost"], "endpoints": eps[i:i + BATCH]}
        ev = stream(CORTEX, req)
        findings += [e["data"] for e in ev if e.get("type") == "finding"]
        trunc += sum(1 for e in ev if e.get("endpoints_handed_in"))
        print(f"    batch {i // BATCH + 1}: {len(eps[i:i+BATCH]):>4} endpoints -> "
              f"{len([e for e in ev if e.get('type') == 'finding']):>4} findings")
    return findings, trunc


def resolved_truth(slug, meta):
    tr = yaml.safe_load(open(f"{meta['dir']}/truth.yml"))
    if tr.get("external"):
        tr["external"]["url"] = f"{meta['seed']}/map/json"
        tr["external"]["solutions"] = f"{meta['seed']}/solutions.json"
        r = external.resolve(tr, target_dir=meta["dir"])
        assert r["resolved"], r.get("reason")
        tr["expected"], tr["negative"] = r["expected"], r["negative"]
        tr["external"] = {**tr["external"], "resolved": True, "via": r.get("via"),
                          "count": r.get("resolved_count")}
        for k in ("reach_scoped_out", "reach_measured", "expected_local"):
            if r.get(k): tr["external"][k] = r[k]
    return tr


def to_finding(slug, d):
    return {"target": slug, "class": d.get("vuln_class"),
            "path": urlparse(d.get("url") or d.get("matched_at") or "").path or "/",
            "param": d.get("param"), "method": d.get("method"), "in": d.get("location")}


if __name__ == "__main__":
    all_truth, all_findings, cost = {}, [], {}
    for slug, meta in TARGETS.items():
        print(f"=== {slug} ===")
        t0 = time.time()
        ev, eps = crawl(meta["seed"])
        csecs = round(time.time() - t0, 1)
        withq = sum(1 for e in eps if e.get("params") or e.get("body"))
        print(f"  crawl: {len(eps)} endpoints in {csecs}s, {withq} of them with a parameter")
        json.dump(eps, open(f"{S}/pipeline_eps_{slug}.json", "w"), indent=1)

        t1 = time.time()
        findings, trunc = inject(meta["seed"], eps, meta["classes"])
        isecs = round(time.time() - t1, 1)
        print(f"  inject: {len(findings)} findings in {isecs}s (truncation notices: {trunc})")

        tr = resolved_truth(slug, meta)
        all_truth[slug] = tr
        all_findings += [to_finding(slug, d) for d in findings]
        cost[slug] = {"seconds": round(csecs + isecs, 1), "requests": 0}

        # The discovery half, stated separately: of the endpoints the answer key
        # expects a finding on, how many did the crawl even reach?
        want = {(e.get("where") or {}).get("path", "").rstrip("/")
                for e in tr.get("expected") or []
                if (e.get("scope") or "black-box") == "black-box"}
        got = {urlsplit(e["url"]).path.rstrip("/") for e in eps}
        reached = len(want & got)
        print(f"  discovery: the crawl reached {reached} of {len(want)} paths "
              f"the key expects a finding on ({reached / max(1, len(want)):.1%})")

    card = scorer.score(all_findings, all_truth, tool="pipeline-mach+cortex-0.0.21", cost=cost)
    print(); print(scorer.render(card))
    json.dump(card, open(f"{S}/pipeline_card.json", "w"), indent=1)
