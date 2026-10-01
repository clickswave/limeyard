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
import urllib.request

ANSWER_KEY = "answer_key"
SELF_SCORED = "self_scored"

TIMEOUT = 10


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

def adapt_crawl_maze(payload, _ext):
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


ADAPTERS = {
    "crawl-maze": adapt_crawl_maze,
}

# Formats the schema names or a truth.yml declares, with no adapter yet. Listed
# so an unresolved target reports why rather than looking like a target nobody
# thought about. Each needs its live payload read before an adapter is written:
# guessing a schema produces a converter that parses one invented shape.
PENDING = {
    "xssmaze-map": "1031 entries at /map/json plus the answer key at "
                   "/solutions.json, with 27 exploitable:false precision controls",
    "crawlground": "self-scored: POST /set-tool, crawl, then read /results.json",
    "vulnerableapp-dast": "the app serves its own DAST list and a grader at "
                          "/scanner/benchmark",
    "owasp-benchmark-csv": "named in truth/schema.md, no target uses it yet",
    "xssmaze-solutions": "named in truth/schema.md; xssmaze itself declares "
                         "`xssmaze-map`, so one of the two names is wrong",
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

    adapted = adapter(payload, ext)
    if not adapted:
        out["reason"] = f"{fmt} payload did not match the expected shape"
        return out

    out.update(adapted)
    out["resolved"] = True
    out["via"] = via
    return out
