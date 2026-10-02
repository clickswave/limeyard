#!/usr/bin/env python3
"""gated - does a truth entry's endpoint answer without credentials?

`scope` is the field that keeps the accounting honest, and it only works if it
is true. Measured 2026-10-02, it is not: DVWA, bWAPP and mutillidae serve a
login page to every unauthenticated request, and their truths label the cases
behind it `black-box`. An unauthenticated scanner is then scored a miss for
nine endpoints it never saw, which measures the lab's labelling rather than the
engine. schema.md already has the right value for this, `authed`, which counts
only when the run seeded credentials and is skipped otherwise.

This is a lint, not a resolver. `scope` lives in the hand-written truth and
should keep living there, because it is limeyard's own editorial judgement
about what a scanner is expected to do, unlike `reach.json` which records a
fact about the target. So this reports a disagreement and writes its evidence
to `gated.json`; a person moves the label and says why in the note.

Three signals, and the first two are unambiguous:

  401 / 403                 the server said so.
  a password input          the response is a login form. Not applied when the
                            requested path is itself a login path, because a
                            login page is correctly a login page.
  a redirect to a login     Location or the final URL names login / signin /
                            auth / session and the request did not.

A body that merely mentions "login" is not a signal. Every application has a
login link in its navigation, and counting that would relabel the whole fleet.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 8

OPEN = "open"
GATED = "gated"
UNKNOWN = "unknown"

LOGIN_PATH = re.compile(r"(?i)(^|/)(login|signin|sign-in|auth|session|account/login)")
# `type=password`, quoted or not, which is what a login form has and a page
# with a link to one does not.
PASSWORD_INPUT = re.compile(r"(?i)<input[^>]*type\s*=\s*[\"']?password")

# A browser's Accept header, because an application can answer a bare client
# with an API error and a browser with a redirect to its login page, and the
# question here is what a crawl would have seen.
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (limeyard scope lint)",
}


def _fetch(url):
    """Returns (status, final_url, body) or None. Redirects are followed,
    because a 302 to the login page is the common shape and the interesting
    fact is where it landed."""
    req = urllib.request.Request(url, headers=dict(HEADERS))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except OSError:
            body = ""
        return e.code, url, body
    except (urllib.error.URLError, OSError, ValueError):
        return None


def reachable(base, timeout=3):
    """Does anything answer at this base URL? Used to pick between the in-lab
    service name and the host-facing one, since the same module runs in both
    places and 127.0.0.1 means something different in each."""
    req = urllib.request.Request(base, headers=dict(HEADERS))
    try:
        with urllib.request.urlopen(req, timeout=timeout):  # noqa: S310
            return True
    except urllib.error.HTTPError:
        return True  # it answered, which is the question
    except (urllib.error.URLError, OSError, ValueError):
        return False


def classify(url, status, final_url, body):
    """Why this endpoint is or is not reachable unauthenticated."""
    if status in (401, 403):
        return GATED, f"the server answered {status}"

    asked = urllib.parse.urlsplit(url)
    landed = urllib.parse.urlsplit(final_url or url)
    asked_is_login = bool(LOGIN_PATH.search(asked.path))

    if not asked_is_login:
        # A redirect that ended somewhere login-shaped, including a query like
        # ?page=login.php, which is how mutillidae does it.
        landed_login = LOGIN_PATH.search(landed.path) or LOGIN_PATH.search(
            landed.query or ""
        )
        if landed_login and (landed.path, landed.query) != (asked.path, asked.query):
            return GATED, f"redirected to {landed.path}" + (
                f"?{landed.query}" if landed.query else ""
            )
        if PASSWORD_INPUT.search(body or ""):
            return GATED, "the response is a login form (it carries a password input)"

    return OPEN, f"answered {status} with no credentials"


def check(entries, host, timeout=TIMEOUT):
    """Classify every entry that declares a path. Returns the dict for
    gated.json. `disagrees` is the only field worth acting on: an entry the
    truth calls black-box that does not answer without credentials."""
    out = {
        "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": host,
        "method": ("request each entry's path with no credentials and a "
                   "browser Accept header, following redirects"),
        "open": {},
        "gated": {},
        "unknown": {},
        "disagrees": [],
    }
    for e in entries or []:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        where = e.get("where") or {}
        path = where.get("path")
        if not path:
            continue
        # Only GET is probed. A POST-only endpoint cannot be asked this
        # question without sending a request that changes something, and a
        # scope label is not worth a write to somebody's target.
        if (where.get("method") or "GET").upper() != "GET":
            out["unknown"][e["id"]] = f"{where.get('method')} only, not probed"
            continue
        url = host.rstrip("/") + path
        got = _fetch(url)
        if got is None:
            out["unknown"][e["id"]] = "no answer"
            continue
        verdict, why = classify(url, *got)
        out[verdict][e["id"]] = why
        if verdict == GATED and (e.get("scope") or "black-box") == "black-box":
            out["disagrees"].append({"id": e["id"], "path": path, "why": why})
    out["totals"] = {k: len(out[k]) for k in ("open", "gated", "unknown")}
    out["totals"]["disagrees"] = len(out["disagrees"])
    return out


def load(target_dir):
    if not target_dir:
        return None
    try:
        with open(os.path.join(target_dir, "gated.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None
