#!/usr/bin/env python3
"""scorer - turn a scanner's findings into a scorecard against limeyard's truth.

The point of the whole lab. A fleet where every target is vulnerable can only
measure recall, and a recall-only score is how a scanner ends up shipping noisy
heuristics. So this counts three things, not one:

  recall     did we find what is there            (expected, scope-filtered)
  precision  did we avoid reporting what is not   (negative entries + unmatched)
  scope      what we correctly did not attempt    (out-of-scope, never counted)

Findings come in loosely, because scanners disagree about shape. The minimum is
a target, a class and a path. Everything else sharpens the match.
"""
import json
import os
import re
import time
from urllib.parse import urlparse

# Aliases scanners actually emit, mapped onto truth/schema.md's class list.
CLASS_ALIASES = {
    "sql-injection": "sqli", "sql_injection": "sqli", "sqlinjection": "sqli",
    "error-based-sqli": "sqli", "blind-sqli": "sqli", "time-based-sqli": "sqli",
    "nosql-injection": "nosqli", "nosql": "nosqli",
    "xss": "xss-reflected", "reflected-xss": "xss-reflected",
    "stored-xss": "xss-stored", "dom-xss": "xss-dom",
    "command-injection": "cmdi", "os-command-injection": "cmdi", "rce": "cmdi",
    "path-traversal": "traversal", "directory-traversal": "traversal",
    "local-file-inclusion": "lfi", "file-inclusion": "lfi",
    "remote-file-inclusion": "rfi",
    "server-side-request-forgery": "ssrf",
    "server-side-template-injection": "ssti", "template-injection": "ssti",
    "xml-external-entity": "xxe",
    "crlf-injection": "crlf", "header-injection": "crlf",
    "open-redirect-param": "open-redirect", "unvalidated-redirect": "open-redirect",
    "insecure-deserialization": "deserialization",
    "race-condition": "race", "toctou": "race",
    "request-smuggling": "smuggling", "desync": "smuggling",
    "prototype-pollution": "proto-pollution",
    "jwt-alg-none": "jwt", "jwt-none": "jwt",
    "mass-assignment-privilege-escalation": "mass-assignment",
    "graphql-introspection": "misconfig", "graphql_introspection": "misconfig",
    "graphql-dos": "dos", "graphql_dos": "dos",
    "graphql-batching": "dos", "graphql_batching": "dos",
    "graphql-sensitive-field": "excessive-exposure",
    "graphql_sensitive_field": "excessive-exposure",
    "graphql-bfla": "bfla", "graphql_bfla": "bfla",
    "idor": "bola", "broken-object-level-authorization": "bola",
    "broken-function-level-authorization": "bfla",
    "broken-object-property-level-authorization": "bopla",
    "excessive-data-exposure": "excessive-exposure",
    "cors-misconfiguration": "cors", "permissive-cors": "cors",
    "information-disclosure": "info-disclosure", "info-leak": "info-disclosure",
    "default-login": "default-creds", "default-credentials": "default-creds",
    "misconfiguration": "misconfig", "technology": "tech", "panel": "panel",
}

# Classes where a finding on the right path but a different-but-related class is
# still the same bug. Kept deliberately tight.
CLASS_FAMILIES = [
    {"lfi", "traversal"},
    {"xss-reflected", "xss-dom"},
    {"bola", "bopla"},
    # A readable phpinfo page is an exposure to one vocabulary and an
    # information disclosure to the other; the bug and the fix are identical.
    # This cuts both ways: it also lets a `exposure` finding match an
    # `info-disclosure` NEGATIVE entry, which is exactly what mirage's bait
    # endpoints are for.
    {"exposure", "info-disclosure"},
]


def norm_class(c):
    if not c:
        return ""
    c = str(c).strip().lower().replace(" ", "-").replace("_", "-")
    return CLASS_ALIASES.get(c, c)


def norm_path(p):
    if not p:
        return "/"
    # Service-kind entries are located by host:port rather than a URL path,
    # because a bare daemon has no path. Keep that form intact on both sides.
    if "://" in p:
        u = urlparse(p)
        if u.port and (not u.path or u.path == "/"):
            return f"{u.hostname}:{u.port}"
        p = u.path or "/"
    elif ":" in p and "/" not in p:
        return p
    p = p.split("?")[0].split("#")[0]
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "/"


def _is_template(seg):
    return seg.startswith("{") and seg.endswith("}")


def path_matches(expected, actual):
    """Exact after normalisation, with {placeholder} segments matching anything."""
    e, a = norm_path(expected), norm_path(actual)
    if e == a:
        return True
    es, as_ = e.split("/"), a.split("/")
    if len(es) != len(as_):
        return False
    for x, y in zip(es, as_):
        if _is_template(x):
            continue
        if x != y:
            return False
    return True


def class_matches(expected, actual):
    e, a = norm_class(expected), norm_class(actual)
    if e == a:
        return True
    return any(e in fam and a in fam for fam in CLASS_FAMILIES)


def _f(finding, *keys):
    for k in keys:
        if finding.get(k):
            return finding[k]
    return None


# Classes that describe the HOST rather than a location on it. Which URL the
# fingerprint happened to match is an implementation detail: Spring Boot is
# identified from whatever path its error handler answers on, and the answer key
# quite reasonably writes the path as "/". Requiring the paths to agree scored a
# correct identification as a miss.
HOST_LEVEL_CLASSES = {"tech", "waf", "panel"}


def entry_matches(entry, finding):
    """A finding matches a truth entry on class + location.

    Loose where scanners legitimately disagree, strict where they should not.
    `in` (query/body/header/cookie) is advisory: a mismatch still matches but is
    flagged, because header and cookie injection points are exactly where
    scanners silently score zero.
    """
    where = entry.get("where") or {}
    if not class_matches(entry.get("class"), _f(finding, "class", "type", "category")):
        return None
    fpath = _f(finding, "path", "url", "endpoint")
    if norm_class(entry.get("class")) in HOST_LEVEL_CLASSES:
        fpath = None  # scored on class alone; see HOST_LEVEL_CLASSES
    if not fpath or norm_path(fpath) == "/":
        # Some stages report a class and nothing else. The graphql stage is the
        # current example: its findings carry vuln_class and a name but no URL.
        # We already know which target the finding came from, so class alone is
        # enough to score it, but the missing location is a real triage gap and
        # is flagged rather than quietly accepted.
        if norm_path(where.get("path") or "/") != "/":
            pass  # fall through to the flag below
    elif not path_matches(where.get("path"), fpath):
        return None
    m = where.get("method")
    fm = _f(finding, "method")
    if m and fm and str(m).upper() != str(fm).upper():
        return None
    p = where.get("param")
    fp = _f(finding, "param", "parameter", "field")
    flags = []
    if not fpath:
        flags.append("matched on class alone; the finding carried no location")
    if p and fp and str(p).lower() != str(fp).lower():
        return None
    if p and not fp:
        # Right class, right path, but the finding did not say which parameter
        # it injected. That is a reporting gap in the finding shape, not grounds
        # for scoring a real detection as a miss. Flagged so it stays visible.
        flags.append(f"matched on class and path; the finding named no parameter "
                     f"(the answer key names '{p}')")
    wi, fi = where.get("in"), _f(finding, "in", "location")
    # `endpoint` is not a mismatch, it is a less specific answer that is true.
    # An authorization probe that compares what two roles get from one endpoint
    # has proved the endpoint is the object; where the object's id happens to
    # sit is something the truth knows and the probe did not need. crAPI's CR1
    # carried a location flag on every run for that reason, and the flag was
    # noise: the detection was right and so was the entry.
    if wi and fi and str(fi).lower() == "endpoint":
        pass
    elif wi and fi and str(wi).lower() != str(fi).lower():
        flags.append(f"location mismatch: expected {wi}, reported {fi}")
    return flags


def score_crawl(tr, fs, scopes=("black-box", "authed")):
    """Reach, not findings. Used by `scoring: crawl`.

    crawl-maze and crawlground ask one question: did the crawler get there. The
    entries carry no class because there is nothing vulnerable to classify, so
    the findings matcher cannot score them, and before this they were scored as
    findings and came back 0 of 0.

    There is no false positive here, so there is no precision. Reaching a URL
    that is not a scored case is what a crawler does all day: crawl-maze serves
    ordinary pages alongside its 91 `.found` resources. Those are counted as
    `off_key` and deliberately kept out of the global `unmatched` pool, which
    exists for findings we failed to document and would otherwise be inflated
    by every page a crawl legitimately walked.
    """
    expected = tr.get("expected") or []
    in_scope = [e for e in expected if e.get("scope", "black-box") in scopes]
    oos = [e for e in expected if e.get("scope") not in scopes]

    want = {}
    for e in in_scope:
        want[norm_path((e.get("where") or {}).get("path"))] = e.get("id")

    seen = set()
    for f in fs:
        p = _f(f, "path", "url", "endpoint")
        if p:
            seen.add(norm_path(p))

    detected = sorted(i for p, i in want.items() if p in seen)
    missed = sorted(i for p, i in want.items() if p not in seen)
    coverage = (len(detected) / len(want)) if want else None

    return {
        "scoring": "crawl",
        "expected_in_scope": len(want),
        "detected": detected,
        "missed": missed,
        "false_positives": [],
        "unmatched": [],
        "off_key": len([p for p in seen if p not in want]),
        "out_of_scope": [e.get("id") for e in oos],
        "location_flags": [],
        "precision": None,
        "recall": round(coverage, 4) if coverage is not None else None,
        "f1": None,
    }


def score(findings, truth, tool="unknown", only=None, scopes=("black-box", "authed"),
          cost=None, seeded=()):
    """findings: [{target, class, path, method?, param?, in?, severity?}]

    `seeded` is the targets whose run seeded credentials, and without it an
    `authed` entry is skipped rather than counted as a miss. schema.md has
    said that is what the label means from the beginning and this did not do
    it: `scopes` defaulted to both and no caller ever passed anything, so
    every run was scored against entries behind a login it never logged into.
    DVWA and bWAPP are nine such entries between them.

    Skipped this way they are reported on their own line, not folded into
    out-of-scope. "Nine cases are out of scope" and "nine cases need
    credentials this run did not seed" are different statements, and only the
    second one tells you to go and seed them.

    `cost` is what the run spent, per target:
    {target: {seconds, requests, truncated}}. A target marked `truncated` had
    its pass cut by a deadline, so its misses are not evidence about the tool.
    It is scored because scan time is a product quality attribute and nothing
    was measuring it: a pass against a 45-endpoint application quietly grew to
    69 minutes, and the scorecard that recorded 43 of 48 said nothing about it.
    A scanner nobody can afford to run is not accurate, it is theoretical.
    """
    per_target, totals = {}, {"expected": 0, "detected": 0, "missed": 0,
                              "false_positive": 0, "unmatched": 0, "out_of_scope": 0,
                              "needs_credentials": 0,
                              "unresolved_external": 0}
    by_class = {}

    grouped = {}
    for f in findings:
        grouped.setdefault(f.get("target") or f.get("workspace") or "?", []).append(f)

    for slug, tr in sorted(truth.items()):
        if only and slug not in only:
            continue
        fs = grouped.get(slug, [])
        expected = [e for e in (tr.get("expected") or [])]
        allowed = set(scopes)
        if slug not in set(seeded):
            allowed.discard("authed")
        in_scope = [e for e in expected if e.get("scope", "black-box") in allowed]
        unseeded = [e for e in expected
                    if e.get("scope") == "authed" and "authed" not in allowed]
        oos = [e for e in expected
               if e.get("scope") not in allowed and e not in unseeded]
        negative = tr.get("negative") or []

        # Four targets declare that their truth lives in the target itself:
        # xssmaze serves 1031 entries plus an answer key, crawl-maze and
        # crawlground serve their expected URL sets, VulnerableApp serves its
        # own grader. Nothing resolves that declaration yet, so these score
        # 0 of 0 and every finding against them lands in `unmatched`, which
        # reads as "we do not document this" when in fact the target does.
        # Record the difference so a reader can see the score is partial.
        ext = tr.get("external") or {}
        unresolved = bool(ext) and not expected and not negative

        # `scoring` has been in truth/schema.md from the start and nothing read
        # it, so every target was scored as findings. `crawl` is the mode that
        # actually needed its own path: its entries carry no class, so the
        # findings matcher scored crawl-maze and crawlground 0 of 0 whether or
        # not their truth resolved. `ports` needs no branch, because
        # openservices locates its entries by host:port in `where.path` and the
        # findings matcher handles that correctly already.
        mode = tr.get("scoring") or "findings"
        if mode == "crawl":
            row = score_crawl(tr, fs, tuple(allowed))
            if unresolved:
                row["external"] = {"resolved": False, "format": ext.get("format"),
                                   "url": ext.get("url"), "reason": ext.get("reason")}
                totals["unresolved_external"] += 1
                totals.setdefault("unresolved_external_targets", []).append(slug)
            per_target[slug] = row
            # Deliberately NOT added to the findings totals. Coverage and
            # detection are different measurements, and folding 91 crawl cases
            # into the same recall denominator as 48 vulnerabilities produces a
            # headline that means nothing. Crawl reach gets its own block.
            c = totals.setdefault("crawl", {"targets": 0, "cases": 0, "reached": 0})
            c["targets"] += 1
            c["cases"] += row["expected_in_scope"]
            c["reached"] += len(row["detected"])
            continue

        used, detected, notes = set(), [], []
        for e in in_scope:
            hit = None
            for i, f in enumerate(fs):
                if i in used:
                    continue
                flags = entry_matches(e, f)
                if flags is not None:
                    hit, used_i = f, i
                    used.add(i)
                    if flags:
                        notes.append({"id": e["id"], "flags": flags})
                    break
            if hit is not None:
                detected.append(e["id"])
        missed = [e["id"] for e in in_scope if e["id"] not in detected]

        fps, unmatched = [], []
        for i, f in enumerate(fs):
            if i in used:
                continue
            neg = next((n for n in negative if entry_matches({**n, "class": n.get("class") or
                        norm_class(_f(f, "class", "type"))}, f) is not None), None)
            rec = {"class": norm_class(_f(f, "class", "type")),
                   "path": norm_path(_f(f, "path", "url")),
                   "param": _f(f, "param", "parameter"),
                   "severity": f.get("severity")}
            if neg:
                fps.append({**rec, "negative_id": neg.get("id"), "note": neg.get("note")})
            else:
                unmatched.append(rec)

        tp, fn, fp = len(detected), len(missed), len(fps)
        prec = tp / (tp + fp) if (tp + fp) else None
        rec_ = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec_ / (prec + rec_)) if (prec and rec_) else None

        per_target[slug] = {
            "expected_in_scope": len(in_scope),
            "detected": detected,
            "missed": missed,
            "false_positives": fps,
            "unmatched": unmatched,
            "out_of_scope": [e["id"] for e in oos],
            "needs_credentials": [e["id"] for e in unseeded],
            "location_flags": notes,
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec_, 4) if rec_ is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        }
        if unresolved:
            per_target[slug]["external"] = {
                "resolved": False,
                "format": ext.get("format"),
                "url": ext.get("url"),
                "reason": ext.get("reason"),
            }
            totals["unresolved_external"] += 1
            totals.setdefault("unresolved_external_targets", []).append(slug)
        elif ext:
            # A resolved target used to record nothing, so the card said why a
            # score was partial but never how the denominator was built. For a
            # target whose key is external and whose scope was corrected by
            # measurement that is the difference between a figure a reader can
            # audit and one they have to take on faith.
            per_target[slug]["external"] = {
                k: v for k, v in (
                    ("resolved", True),
                    ("format", ext.get("format")),
                    ("via", ext.get("via")),
                    ("count", ext.get("count")),
                    ("reach_scoped_out", ext.get("reach_scoped_out")),
                    ("reach_measured", ext.get("reach_measured")),
                    ("expected_local", ext.get("expected_local")),
                    ("negative_local", ext.get("negative_local")),
                ) if v is not None
            }
        totals["expected"] += len(in_scope)
        totals["detected"] += tp
        totals["missed"] += fn
        totals["false_positive"] += fp
        totals["unmatched"] += len(unmatched)
        totals["out_of_scope"] += len(oos)
        totals["needs_credentials"] += len(unseeded)

        for e in in_scope:
            c = norm_class(e.get("class"))
            b = by_class.setdefault(c, {"expected": 0, "detected": 0})
            b["expected"] += 1
            if e["id"] in detected:
                b["detected"] += 1

    if "crawl" in totals:
        c = totals["crawl"]
        c["coverage"] = round(c["reached"] / c["cases"], 4) if c["cases"] else None

    tp, fn, fp = totals["detected"], totals["missed"], totals["false_positive"]
    totals["precision"] = round(tp / (tp + fp), 4) if (tp + fp) else None
    totals["recall"] = round(tp / (tp + fn), 4) if (tp + fn) else None
    if totals["precision"] and totals["recall"]:
        totals["f1"] = round(2 * totals["precision"] * totals["recall"] /
                             (totals["precision"] + totals["recall"]), 4)
    else:
        totals["f1"] = None

    for c, b in by_class.items():
        b["recall"] = round(b["detected"] / b["expected"], 4) if b["expected"] else None

    # Cost, alongside correctness. Reported per target and in total, with the
    # slowest named: an average hides the one target that took an hour.
    cost = cost or {}
    if cost:
        secs = {t: float(v.get("seconds") or 0) for t, v in cost.items()}
        reqs = {t: int(v.get("requests") or 0) for t, v in cost.items()}
        slowest = max(secs, key=secs.get) if secs else None
        totals["seconds"] = round(sum(secs.values()), 1)
        totals["requests"] = sum(reqs.values())
        totals["slowest_target"] = slowest
        totals["slowest_seconds"] = round(secs.get(slowest, 0), 1) if slowest else None
        for t, v in cost.items():
            if t in per_target:
                per_target[t]["seconds"] = round(float(v.get("seconds") or 0), 1)
                per_target[t]["requests"] = int(v.get("requests") or 0)
                # Sites the engine could not get a baseline for. They were not
                # tested, and a recall figure that counts them as clean misses is
                # measuring the load the pass applied, not the tool.
                if v.get("skipped_sites"):
                    per_target[t]["skipped_sites"] = int(v["skipped_sites"])
                # Where the time went, per class. The ratio is what tells a
                # slow scan from an expensive one.
                if v.get("by_class"):
                    per_target[t]["by_class"] = str(v["by_class"])
                if v.get("truncated"):
                    per_target[t]["truncated"] = True
        # A run the clock cut short did not miss what it never reached, and a
        # recall figure that does not say so is worse than no figure: it turns
        # "we ran out of time" into "the scanner cannot find this". Named at
        # the top of the card so it cannot be read past.
        cut = sorted(t for t, v in cost.items() if v.get("truncated"))
        if cut:
            totals["truncated_targets"] = cut
            totals["recall_is_a_lower_bound"] = True

    return {
        "tool": tool,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totals": totals,
        "by_class": dict(sorted(by_class.items())),
        "by_target": per_target,
    }


def save(card, truth_dir):
    """Write a card, without ever silently replacing another one.

    The name was date plus tool, which collides the moment two runs happen on
    one day with one engine: scoring xssmaze and then VulnerableApp overwrote
    the first card with the second, and only a commit made it recoverable. A
    scorecard is a record, so a second run gets a second file.

    A single-target run says which target in the name, because that is the
    thing a reader wants to tell apart. Anything already there is suffixed
    rather than touched.
    """
    d = os.path.join(truth_dir, "scorecards")
    os.makedirs(d, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d")
    clean = lambda v: re.sub(r"[^a-zA-Z0-9_.-]", "-", str(v))
    tool = clean(card.get("tool", "unknown"))
    targets = list(card.get("by_target") or {})
    stem = f"{stamp}-{tool}"
    if len(targets) == 1:
        stem = f"{stem}-{clean(targets[0])}"
    path = os.path.join(d, f"{stem}.json")
    n = 2
    while os.path.exists(path):
        path = os.path.join(d, f"{stem}-{n}.json")
        n += 1
    with open(path, "w") as f:
        json.dump(card, f, indent=2, sort_keys=False)
        f.write("\n")
    return path


def _ids(ids, cap=6):
    """Name a few misses, then count the rest.

    Fine while the biggest target had four cases. xssmaze resolves to 1013, and
    a run that misses 713 of them printed every id on one line, which is not a
    report. The full list is in the JSON for whoever wants to diff two runs.
    """
    if len(ids) <= cap + 2:
        return ",".join(ids)
    return ",".join(ids[:cap]) + f" +{len(ids) - cap} more"


def render(card):
    """Terminal summary. The numbers that matter, in the order they matter."""
    t = card["totals"]
    out = [f"scorecard  tool={card['tool']}  {card['generated']}", ""]
    def pct(v):
        return "  -  " if v is None else f"{v * 100:5.1f}%"
    out.append(f"  recall     {pct(t['recall'])}   {t['detected']}/{t['expected']} in-scope expected")
    out.append(f"  precision  {pct(t['precision'])}   {t['false_positive']} false positives")
    out.append(f"  f1         {pct(t['f1'])}")
    out.append(f"  unmatched  {t['unmatched']:5d}     findings we do not document (promote or investigate)")
    if t.get("unresolved_external"):
        names = ", ".join(t.get("unresolved_external_targets") or [])
        out.append(f"  unscored   {t['unresolved_external']:5d}     "
                   f"targets whose truth is external and was not fetched: {names}")
        out.append("                       their findings sit in unmatched, so the figures "
                   "above are a partial score")
    out.append(f"  skipped    {t['out_of_scope']:5d}     out-of-scope, never counted")
    if t.get("needs_credentials"):
        # Distinct from out-of-scope on purpose. These are cases a scanner is
        # expected to find, behind a login this run did not seed, so the number
        # is an instruction rather than an exclusion.
        out.append(f"  unseeded   {t['needs_credentials']:5d}     authed, and this run "
                   f"seeded no credentials for them")
    if t.get("crawl"):
        c = t["crawl"]
        cov = "  -  " if c.get("coverage") is None else f"{c['coverage'] * 100:5.1f}%"
        out.append(f"  crawl      {cov}   {c['reached']}/{c['cases']} reachable cases "
                   f"across {c['targets']} target(s), scored separately")
    out.append("")
    out.append("  by class")
    for c, b in card["by_class"].items():
        out.append(f"    {c:22} {b['detected']}/{b['expected']}")
    out.append("")
    out.append("  by target")
    for slug, r in card["by_target"].items():
        bits = f"{len(r['detected'])}/{r['expected_in_scope']}"
        extra = []
        if r.get("scoring") == "crawl":
            # Naming 51 missed ids is not a report, it is a wall. The ids are in
            # the JSON for whoever wants to diff two runs.
            if r["missed"]:
                extra.append(f"{len(r['missed'])} unreached")
            if r.get("off_key"):
                extra.append(f"{r['off_key']} off-key")
            if (r.get("external") or {}).get("resolved") is False:
                extra.append("truth not fetched")
            out.append(f"    {slug:14} {bits:>7}   {'; '.join(extra)}")
            continue
        if (r.get("external") or {}).get("resolved") is False:
            extra.append("truth not fetched")
        # A corrected denominator has to be visible on the card. A scope change
        # that only shows up as a smaller number is a scope change nobody can
        # audit, and this one moves recall by tens of points.
        ext = r.get("external") or {}
        if ext.get("reach_scoped_out"):
            extra.append(f"{ext['reach_scoped_out']} unreachable, measured "
                         f"{ext.get('reach_measured') or 'date unknown'}")
        if ext.get("expected_local"):
            extra.append(f"{ext['expected_local']} promoted locally")
        if r["missed"]:
            extra.append("missed " + _ids(r["missed"]))
        if r["false_positives"]:
            extra.append(f"{len(r['false_positives'])} FP")
        if r["location_flags"]:
            extra.append(f"{len(r['location_flags'])} location flag")
        out.append(f"    {slug:14} {bits:>7}   {'; '.join(extra)}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    data = json.load(sys.stdin)
    print(render(score(data.get("findings", []), data.get("truth", {}),
                       tool=data.get("tool", "stdin"))))
