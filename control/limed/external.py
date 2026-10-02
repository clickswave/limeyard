#!/usr/bin/env python3
"""external - resolve a truth.yml `external:` block into something scoreable.

Four targets do not ship an answer key in their truth.yml, because they already
serve one themselves and restating it here would mean maintaining a copy that
drifts. `truth/schema.md` has described the block since the beginning and
nothing read it, so those four scored 0 of 0 and every finding against them
landed in `unmatched`, which reads as "we do not document this" when the target
documents it in detail. xssmaze alone serves 1031 entries and an answer key.

Two kinds, and the difference decides who does the scoring:

  ANSWER_KEY   the target says what SHOULD be found. It resolves into ordinary
               `expected` / `negative` entries and the local matcher scores it
               exactly like a hand-written truth.yml. crawl-maze and xssmaze
               are this shape.

  SELF_SCORED  the target says what WAS found. Crawlground hands out markers
               linked from nowhere else and records which tool reached them, so
               there is nothing to match locally: the verdict is imported.
               Conflating the two would mean inventing an answer key from a
               result, which is how a benchmark starts grading its own homework.

No third-party imports: the control image is `docker:29-cli` plus python3 and
py3-yaml, so HTTP is `urllib` and nothing here may grow a dependency.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

ANSWER_KEY = "answer_key"
SELF_SCORED = "self_scored"

# Every declared source is on the lab network or loopback, so it answers in
# milliseconds or it is not running. A long timeout only means a cold lab makes
# `lime truth` hang for four targets in a row.
TIMEOUT = 4


# ----------------------------------------------------------------- fetching ---

def http_json(url, timeout=TIMEOUT):
    """GET a JSON document. Returns None rather than raising: a cold lab is the
    normal case for an offline `lime truth` dump, and a target being down must
    not fail a scoring run that has already happened."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def file_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------- adapters ---

def adapt_crawl_maze(payload, _ext, _extra):
    """Google's Security Crawl Maze: a flat list of 91 paths a crawler should
    reach, every one ending `.found` so a miss is identifiable by eye.

    There is nothing vulnerable here and so no class on these entries. The
    `crawl` scoring mode matches on path alone, which is the whole question.

    No negative entries: the maze publishes what should be found and says
    nothing about what should not, so inventing precision controls here would
    be inventing ground truth.
    """
    if not isinstance(payload, list):
        return None
    paths = sorted({p for p in payload if isinstance(p, str) and p.strip()})
    return {
        "kind": ANSWER_KEY,
        "expected": [
            {"id": f"CM{i:03d}", "scope": "black-box", "where": {"path": p}}
            for i, p in enumerate(paths, 1)
        ],
        "negative": [],
        "resolved_count": len(paths),
    }


# XSSMaze's own vocabulary, onto truth/schema.md's class list. Mapped
# explicitly rather than by prefix so that a class upstream adds later shows up
# as unrecognised instead of being silently folded into xss-reflected and
# quietly changing the denominator.
XSSMAZE_CLASSES = {
    "reflected-html": "xss-reflected",
    "reflected-attr": "xss-reflected",
    "reflected-js": "xss-reflected",
    "dom": "xss-dom",
    "stored": "xss-stored",
    "prototype-pollution": "proto-pollution",
    # Not ssti: these are AngularJS and Vue `{{ }}` expressions evaluated in
    # the browser. See schema.md's class list.
    "csti": "csti",
    "non-xss-control": None,   # the precision controls, see below
}

# XSSMaze says where a payload is delivered; schema.md's `in` is narrower.
# `fragment` has no equivalent on purpose: a fragment never leaves the browser,
# so there is no request location to name.
XSSMAZE_DELIVERY = {
    "query": "query", "body": "body", "header": "header",
    "cookie": "cookie", "path": "path", "referer": "header",
    "fragment": "fragment",
}


def xssmaze_param(ep, solution):
    """Which parameter the answer key certifies, not the first one declared.

    The adapter used to take params[0], and on a multi-parameter endpoint that
    is frequently the wrong one. xssmaze says so itself: multiparam-level5 is
    "only name is exploitable" against params ['prefix', 'name', 'suffix'],
    hpp-level2 is "the injectable parameter is q" against ['query', 'q'], and
    multireflect-level7 is "only email is reflected raw" against
    ['name', 'email']. Each of those scored a correct detection as a miss and
    filed the engine's answer under unmatched at the same time, so one truth
    bug cost two entries.

    The note says which, but prose is not something to parse. /solutions.json
    carries a working exploit URL per maze, and diffing its query against the
    baseline query in the endpoint's own url names the parameter the payload
    goes in. That is upstream's certification, expressed as data.

    A scanner that finds a different parameter that also works lands in
    `unmatched`, which is what unmatched is for: a finding to promote or
    investigate, never recall the engine did not earn.
    """
    real = [x for x in (ep.get("params") or [])
            if isinstance(x, str) and x and not x.startswith("#")]
    if not real:
        return None
    # `:path` and friends name a channel, not a request parameter. Dropping it
    # lets path+class carry the match, since the path is the location.
    if all(x.startswith(":") for x in real):
        return None
    plain = [x for x in real if not x.startswith(":")]
    if len(plain) < 2:
        return plain[0] if plain else None

    want = (solution or {}).get("url")
    if not isinstance(want, str) or "?" not in want:
        return plain[0]
    try:
        base = dict(urllib.parse.parse_qsl(
            urllib.parse.urlsplit(ep.get("url") or "").query, keep_blank_values=True))
        sol = dict(urllib.parse.parse_qsl(
            urllib.parse.urlsplit(want).query, keep_blank_values=True))
    except ValueError:
        return plain[0]
    changed = [k for k in plain if k in sol and sol.get(k) != base.get(k)]
    if len(changed) == 1:
        return changed[0]
    # Nothing changed, or several did and the key does not single one out.
    # Keep the declared order rather than inventing a preference.
    return changed[0] if changed else plain[0]


def adapt_xssmaze_map(payload, _ext, extra):
    """XSSMaze serves /map/json: every endpoint with its class, delivery
    channel, sources, sinks and an `exploitable` flag.

    Two properties make it unusually fair to score against, and both are used
    here rather than flattened away.

    `exploitable: false` marks an endpoint that looks vulnerable and is not.
    The one that makes the point is bugbounty-level10, whose body is HTML but
    whose content type is application/json, so no browser sniffs it into a
    document. Those become `negative` entries, with no class, so that reporting
    anything at all there is a false positive. This is the half of the
    benchmark that was missing: a precision figure needs somewhere to be wrong.

    `reach: client` marks a flow that never touches an HTTP response, like
    codeexec-level3 reading location.hash into script.text. A request-only
    engine cannot see it, so it is scoped out rather than counted as a miss.
    Scoring those as failures would measure the protocol, not the scanner.

    Entry ids are upstream's `name`, which is unique across all 1064 and
    survives upstream reordering, unlike a generated index. schema.md says ids
    are referenced by scorecards forever, so they had better be stable.
    """
    eps = (payload or {}).get("endpoints")
    if not isinstance(eps, list) or not eps:
        return None

    # /solutions.json is keyed by the same name and carries the payload that
    # works plus the bypass it needs. Not required to match a finding, which
    # only needs class and location, but it turns a missed id from a name into
    # a reason, which is the difference between a scorecard and a to-do list.
    sol = extra.get("solutions") if isinstance(extra, dict) else None
    sol = sol if isinstance(sol, dict) else {}

    # The measured half of the scope decision. Empty unless the target has a
    # committed reach.json, so every other target is unaffected.
    try:
        import reach
        unreach, unreach_on = reach.unreachable(
            (extra or {}).get("target_dir"), eps)
    except Exception:
        unreach, unreach_on = set(), None

    expected, negative, unknown = [], [], set()
    for e in eps:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        v = e.get("vuln") or {}
        raw = (e.get("url") or "/").split("?")[0].split("#")[0] or "/"
        where = {"path": raw}
        if e.get("method"):
            where["method"] = e["method"]
        chosen = xssmaze_param(e, sol.get(e["name"]))
        if chosen:
            where["param"] = chosen
        delivery = (v.get("delivery") or [None])[0]
        where_in = XSSMAZE_DELIVERY.get(delivery)
        if where_in:
            where["in"] = where_in

        if not v.get("exploitable"):
            negative.append({"id": e["name"], "where": where,
                             "note": v.get("note") or e.get("desc")})
            continue

        cls = v.get("class")
        mapped = XSSMAZE_CLASSES.get(cls, cls)
        if cls not in XSSMAZE_CLASSES:
            unknown.add(cls)
        # `reach: client` is upstream's own flag. `unreach` is the measured
        # correction to it: endpoints upstream calls server-reaching whose
        # bytes provably never appear in a response. Both mean the same thing
        # to a request-only engine, so both score the same way.
        unreachable = v.get("reach") == "client" or e["name"] in unreach
        expected.append({
            "id": e["name"],
            "class": mapped,
            "scope": "out-of-scope" if unreachable else "black-box",
            "where": where,
            "confirm": ((sol.get(e["name"]) or {}).get("context")
                        or v.get("note") or e.get("desc")),
        })

    out = {
        "kind": ANSWER_KEY,
        "expected": expected,
        "negative": negative,
        "resolved_count": len(expected) + len(negative),
    }
    if unknown:
        out["unrecognised_classes"] = sorted(x for x in unknown if x)
    # Say that a denominator was corrected and on what date. A scope change
    # nobody can see on the card is a scope change that flatters the scanner.
    if unreach:
        out["reach_scoped_out"] = len(unreach)
        out["reach_measured"] = unreach_on
    return out


# OWASP VulnerableApp's own vulnerability names, onto schema.md's class list.
# Only where the meaning is the same: schema.md says to extend the class list
# deliberately, not per target, so a type with no equivalent is recorded and
# scoped out rather than wedged into the nearest-looking class.
VULNERABLEAPP_CLASSES = {
    "ERROR_BASED_SQL_INJECTION": "sqli",
    "UNION_BASED_SQL_INJECTION": "sqli",
    "BLIND_SQL_INJECTION": "sqli",
    "REFLECTED_XSS": "xss-reflected",
    "PERSISTENT_XSS": "xss-stored",
    "PATH_TRAVERSAL": "traversal",
    "COMMAND_INJECTION": "cmdi",
    "XXE": "xxe",
    "SIMPLE_SSRF": "ssrf",
    "OPEN_REDIRECT_3XX_STATUS_CODE": "open-redirect",
    "HEADER_INJECTION": "crlf",
    "WEB_CACHE_POISONING": "cache-poisoning",
    "CLIENT_SIDE_VULNERABLE_JWT": "jwt",
    "SERVER_SIDE_VULNERABLE_JWT": "jwt",
    "INSECURE_CONFIGURATION_JWT": "jwt",
    "INSECURE_DIRECT_OBJECT_REFERENCE": "bola",
    "USERNAME_ENUMERATION": "info-disclosure",
    "CLICKJACKING": "misconfig",
    "UNCONTROLLED_RESOURCE_CONSUMPTION": "dos",
    "DENIAL_OF_SERVICE": "dos",
    "SESSION_FIXATION": "session",
    "PREDICTABLE_SESSION_ID": "session",
    "OBSCURED_PREDICTABLE_SESSION_ID": "session",
    "MISSING_LOGOUT_INVALIDATION": "session",
}


def _va_id(path, kind):
    """A stable id from the module and level, because upstream gives no name.

    VulnerableApp's paths are `/VulnerableApp/<Module>/LEVEL_<n>`, which is
    exactly the identity of a case and does not move when the list is
    reordered. The type is appended because one URL can carry several.
    """
    parts = [x for x in path.strip("/").split("/") if x and x != "VulnerableApp"]
    stem = "-".join(parts[-2:]) if parts else "root"
    return f"{stem}:{kind}".lower()


def adapt_vulnerableapp_dast(payload, _ext, _extra):
    """VulnerableApp serves /VulnerableApp/scanner/dast: every case as a URL, a
    method, a variant and the vulnerability types it carries.

    The `variant` field is why this target is worth resolving. 17 of the 155
    cases are `SECURE`, the hardened twin of a vulnerable level, which is the
    shape schema.md names when it says a target that ships a hardened twin
    expresses it in `negative`. The twin keeps its class, so reporting that
    class there is a false positive while a genuinely different finding at the
    same URL is still just a finding.

    Entries carry no parameter. The matcher treats an entry with no `param` as
    matching any finding on that path, which is the right reading here: the
    list says where the vulnerability is, not which input reaches it.

    Of the 38 types upstream uses, the crypto and password-reset families have
    no equivalent in schema.md's class list (WEAK_PASSWORD_HASHING,
    PLAINTEXT_PASSWORD_STORAGE, PREDICTABLE_PASSWORD_RESET_TOKEN and so on).
    Those are scoped out and reported, so extending the class list stays a
    deliberate decision with the count in front of it, rather than a quiet
    mapping into `misconfig` that would make recall look better than it is.
    """
    if not isinstance(payload, list) or not payload:
        return None

    expected, negative, unmapped = [], [], {}
    for e in payload:
        if not isinstance(e, dict) or not e.get("url"):
            continue
        raw = e["url"].split("?")[0].split("#")[0]
        if "://" in raw:
            raw = "/" + raw.split("://", 1)[1].split("/", 1)[1] if "/" in raw.split("://", 1)[1] else "/"
        where = {"path": raw}
        if e.get("method"):
            where["method"] = e["method"]
        secure = str(e.get("variant", "")).upper() == "SECURE"

        for kind in (e.get("vulnerabilityTypes") or []):
            cls = VULNERABLEAPP_CLASSES.get(kind)
            if cls is None:
                unmapped[kind] = unmapped.get(kind, 0) + 1
            row = {"id": _va_id(raw, kind), "class": cls, "where": dict(where)}
            if secure:
                row["note"] = f"SECURE variant: the fixed twin of {kind}"
                negative.append(row)
            else:
                row["scope"] = "black-box" if cls else "out-of-scope"
                row["confirm"] = kind if cls else f"{kind}: no class in schema.md"
                expected.append(row)

    out = {
        "kind": ANSWER_KEY,
        "expected": expected,
        "negative": negative,
        "resolved_count": len(expected) + len(negative),
    }
    if unmapped:
        out["unmapped_types"] = dict(sorted(unmapped.items()))
    return out


def adapt_crawlground(payload, _ext, _extra):
    """ZAP's Crawlground: 59 tests, each with a page at /test/<cat>/<id> and a
    marker at /score/<cat>/<id> linked from nowhere else, so the only way to
    reach a marker is to operate the control that leads to it.

    Resolved as an answer key rather than as the target's own verdict, which is
    a deliberate choice and the opposite of what `set_tool` invites.

    Crawlground records which named tool hit each marker, and reading that back
    would be letting the benchmark grade itself: the store is mutable, keyed on
    a name set by a POST, and shared by every run that forgot to reset. Every
    other target in the lab is scored on what the scanner reported, and keeping
    one model matters more than the small amount the target's own bookkeeping
    adds. So `set_tool` stays unused and the markers become ordinary `crawl`
    entries, scored exactly like crawl-maze's.

    Marker paths are derived, because upstream does not publish them: the test
    id is `<category>.<rest>` and the marker is `/score/<category>/<rest>`.
    Verified against the live target on 2026-10-01, all 59 ids conform to that
    shape and the derived paths answer 200.

    One caveat worth stating. A scanner that extracted a marker URL without
    following it would score here, and the measure assumes reporting implies
    reaching. Crawlground's own design is what makes that safe: markers are
    linked from nowhere, so for the JS-driven cases there is no href to lift.
    """
    tests = (payload or {}).get("tests")
    if not isinstance(tests, list) or not tests:
        return None

    expected = []
    for t in tests:
        if not isinstance(t, dict):
            continue
        tid, cat = t.get("id"), t.get("category")
        if not tid or not cat or "." not in tid:
            continue
        expected.append({
            "id": tid,
            "scope": "black-box",
            "where": {"path": f"/score/{cat}/{tid.split('.', 1)[1]}"},
            "confirm": t.get("name") or t.get("description"),
        })
    if not expected:
        return None
    return {
        "kind": ANSWER_KEY,
        "expected": expected,
        "negative": [],
        "resolved_count": len(expected),
    }


ADAPTERS = {
    "crawl-maze": adapt_crawl_maze,
    "xssmaze-map": adapt_xssmaze_map,
    "vulnerableapp-dast": adapt_vulnerableapp_dast,
    "crawlground": adapt_crawlground,
}

# Formats the schema names or a truth.yml declares, with no adapter yet. Listed
# so an unresolved target reports why rather than looking like a target nobody
# thought about. Each needs its live payload read before an adapter is written:
# guessing a schema produces a converter that parses one invented shape.
PENDING = {
    "owasp-benchmark-csv": "named in truth/schema.md, no target uses it yet",
    "wavsep-paths": "named in truth/schema.md, no target uses it yet",
}


# ------------------------------------------------------------------ resolve ---

def resolve(tr, target_dir=None, offline=False):
    """Resolve `tr["external"]`, returning a dict to merge into the truth.

    Always returns a dict carrying `resolved` so the scorecard can state the
    outcome. A target whose truth could not be reached is reported as
    unresolved, never as a target with nothing to find.

    `target_dir` lets a declared `file:` be read from the fetched source, which
    is how crawl-maze resolves with the lab cold: its expected-results.json is
    committed in the upstream tree limeyard clones. `offline` skips HTTP.
    """
    ext = (tr or {}).get("external") or {}
    if not ext:
        return {}

    fmt = ext.get("format")
    out = {"external": dict(ext), "resolved": False}

    adapter = ADAPTERS.get(fmt)
    if adapter is None:
        out["reason"] = PENDING.get(fmt, f"no adapter for format {fmt!r}")
        return out

    payload, via = None, None

    # A committed file beats the network: it works with the lab cold and it is
    # the same bytes the target would serve.
    rel = ext.get("file")
    if rel and target_dir:
        payload = file_json(os.path.join(target_dir, "src", rel))
        if payload is None:
            payload = file_json(os.path.join(target_dir, rel))
        if payload is not None:
            via = f"file:{rel}"

    if payload is None and not offline and ext.get("url"):
        payload = http_json(ext["url"])
        if payload is not None:
            via = ext["url"]

    if payload is None:
        out["reason"] = ("could not read the declared source"
                         + (" (offline)" if offline else ""))
        return out

    # Secondary sources the block declares. Optional by design: a missing
    # answer key costs detail in `confirm`, never the score itself.
    extra = {"target_dir": target_dir}
    if not offline and ext.get("solutions"):
        extra["solutions"] = http_json(ext["solutions"])

    adapted = adapter(payload, ext, extra)
    if not adapted:
        out["reason"] = f"{fmt} payload did not match the expected shape"
        return out

    out.update(adapted)

    # Hand-written entries survive. `resolve` used to hand back only what the
    # adapter built and every caller assigned it over `tr["expected"]`, so an
    # entry written into a truth.yml beside an `external:` block was silently
    # discarded. That is the one place a locally verified finding has to live:
    # upstream's key is upstream's, and a real vulnerability the key does not
    # document cannot be added to it. Four reflected XSS on VulnerableApp's
    # ErrorBasedSQLInjection levels are exactly that case.
    #
    # Local entries come first and win on id, so a truth.yml can also correct
    # an upstream entry rather than only add to it.
    for key in ("expected", "negative"):
        local = [x for x in (tr.get(key) or []) if isinstance(x, dict)]
        if not local:
            continue
        seen = {x.get("id") for x in local if x.get("id")}
        merged = list(local)
        merged += [x for x in (out.get(key) or [])
                   if not (x.get("id") and x["id"] in seen)]
        out[key] = merged
        out[f"{key}_local"] = len(local)
    out["resolved_count"] = len(out.get("expected") or []) + len(out.get("negative") or [])

    out["resolved"] = True
    out["via"] = via
    return out
