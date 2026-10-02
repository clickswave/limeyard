#!/usr/bin/env python3
"""cortex's authorization engine against OWASP crAPI.

Two fresh accounts that own nothing, an anonymous identity, and the vehicle ids
the community feed hands out, which is the whole point of CR2: it seeds the
identifiers that make CR1 reachable.

The anonymous identity is not optional and this script learned that the hard
way. The oracle replays every endpoint as every identity and compares, and two
authenticated 200s on their own say nothing: a public endpoint looks exactly
like a broken one. The unauthenticated row is what turns it into "authentication
works and authorization does not". Without it this run reported 0 of 4 on two
BOLAs that had been hand-verified minutes earlier.

Written down because the first run of this was done by hand and the score it
produced could not be reproduced by anyone, including by me a day later.
"""
import json, socket, sys, time, urllib.error, urllib.request
from urllib.parse import urlparse
sys.path.insert(0, "/home/kew/projects/clickswave/projects/limeyard/control/limed")
import yaml, scorer

H = "http://127.0.0.1:7010"
CORTEX = ("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 4488)
TDIR = "/home/kew/projects/clickswave/projects/limeyard/targets/api/crapi"
S = "/tmp/claude-1000/-home-kew-projects-clickswave/913b853d-11fa-42b3-a6bd-6b6c1de6ebb1/scratchpad"
# Two identities with no relationship to each other and no objects of their own.
# A pair that owns nothing is what makes a 200 unambiguous: there is nothing
# either of them is entitled to see.
#
# Fresh every run, because crAPI's database outlives the containers and the
# first version of this reused a fixed address. The account was still there
# from a previous session under a password this script no longer knew, signup
# answered "already registered", login answered "invalid credentials", and the
# run died at the first step. A driver that depends on state from a run nobody
# recorded is not reproducible, which was the whole reason for writing it down.
_RUN = time.strftime("%Y%m%d%H%M%S", time.gmtime())
USERS = [(f"cfx-authz-a-{_RUN}@example.com", "Cfx-Authz-A1!", f"98{_RUN[-8:]}", "cfx authz a"),
         (f"cfx-authz-b-{_RUN}@example.com", "Cfx-Authz-B1!", f"97{_RUN[-8:]}", "cfx authz b")]


def api(path, data=None, token=None, method=None, timeout=20):
    req = urllib.request.Request(
        H + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method or ("POST" if data is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)


def token_for(email, password, number, name):
    code, body = api("/identity/api/auth/signup",
                     {"name": name, "email": email, "number": number,
                      "password": password})
    if code not in (200, 201):
        print(f"  signup {email}: {code} {body[:120]}")
    code, body = api("/identity/api/auth/login", {"email": email, "password": password})
    if code != 200:
        print(f"  login {email}: {code} {body[:160]}")
        return None
    try:
        return json.loads(body).get("token")
    except Exception:
        return None


def vehicle_ids(token, want=3):
    """The uuids the community feed leaks, which is CR2 feeding CR1."""
    out, seen = [], set()
    code, body = api("/community/api/v2/community/posts/recent", token=token)
    if code == 200:
        def walk(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if k in ("vehicleid", "vehicleId", "uuid", "vin") and isinstance(x, str) and len(x) >= 32:
                        if x not in seen:
                            seen.add(x); out.append(x)
                    walk(x)
            elif isinstance(v, list):
                for x in v: walk(x)
        try: walk(json.loads(body))
        except Exception: pass
    return out[:want]


def endpoints(vids):
    eps = [{"method": "GET", "url": f"{H}/community/api/v2/community/posts/recent"},
           {"method": "GET", "url": f"{H}/workshop/api/mechanic/"},
           {"method": "GET", "url": f"{H}/identity/api/v2/user/dashboard"}]
    for v in vids:
        eps.append({"method": "GET", "url": f"{H}/identity/api/v2/vehicle/{v}/location"})
    # CR6: any authenticated caller reads any mechanic report.
    for i in range(1, 6):
        eps.append({"method": "GET",
                    "url": f"{H}/workshop/api/mechanic/mechanic_report?report_id={i}"})
    return eps


def run(eps, identities, timeout=1800):
    req = {"operation": "authz", "response": "stream", "target": H,
           "timeout_ms": 20000, "endpoints": eps, "identities": identities,
           "scope": ["127.0.0.1", "localhost"]}
    s = socket.create_connection(CORTEX, timeout=timeout); s.settimeout(timeout)
    s.sendall((json.dumps(req) + "\n").encode())
    ev = []
    for line in s.makefile("rb"):
        line = line.strip()
        if not line: continue
        try: e = json.loads(line)
        except Exception: continue
        ev.append(e)
        if e.get("type") in ("done", "error"): break
    s.close(); return ev


def to_finding(d):
    u = d.get("url") or d.get("matched_at") or ""
    p = urlparse(u)
    return {"target": "crapi", "class": d.get("vuln_class"),
            "path": p.path or "/", "param": d.get("param"),
            "method": d.get("method"), "in": d.get("location")}


if __name__ == "__main__":
    toks = {}
    for email, pw, num, name in USERS:
        t = token_for(email, pw, num, name)
        if not t:
            sys.exit(f"could not get a token for {email}; is crAPI fully up?")
        toks[email] = t
    json.dump(toks, open(f"{S}/crapi_toks.json", "w"), indent=1)
    vids = vehicle_ids(toks[USERS[0][0]])
    json.dump(vids, open(f"{S}/crapi_vids.json", "w"), indent=1)
    print(f"2 identities, {len(vids)} vehicle id(s) from the community feed")

    identities = [{"role": f"user{i+1}", "auth": {"headers": {"Authorization": f"Bearer {toks[u[0]]}"}}}
                  for i, u in enumerate(USERS)]
    # The row that makes the rest mean anything.
    identities.append({"role": "anonymous", "auth": {}})
    eps = endpoints(vids)
    print(f"{len(eps)} endpoints as {len(identities)} identities, one of them anonymous")

    t0 = time.time()
    ev = run(eps, identities)
    findings = [e["data"] for e in ev if e.get("type") == "finding"]
    secs = round(time.time() - t0, 1)
    print(f"{len(findings)} findings in {secs}s\n")
    for f in findings:
        print(f"  {f.get('vuln_class'):20} {urlparse(f.get('url') or '').path}")
        print(f"      {(f.get('description') or '')[:170]}")
    json.dump(findings, open(f"{S}/crapi_authz.json", "w"), indent=1)

    tr = yaml.safe_load(open(f"{TDIR}/truth.yml"))
    # Credentials were seeded, so the `authed` entries count. Without this the
    # scorer skips them, which is correct for a run that did not log in and
    # wrong for this one.
    card = scorer.score([to_finding(d) for d in findings], {"crapi": tr},
                        tool="cortex-0.0.21-authz", seeded={"crapi"},
                        cost={"crapi": {"seconds": secs, "requests": 0}})
    print(); print(scorer.render(card))
    json.dump(card, open(f"{S}/crapi_card.json", "w"), indent=1)
