#!/usr/bin/env python3
"""reach - measure whether a target's declared reach metadata is true.

A target that declares, per endpoint, whether a flow touches an HTTP response
is handing the lab the single most important fact for scoring a request-only
scanner: whether there is anything for it to see. xssmaze does this with a
`reach` of server or client, and `external.py` scopes the client ones out of
the recall denominator rather than counting them as misses.

The flag turned out to be wrong in one direction. Measured 2026-10-01T23:25Z,
95 of the 1013 endpoints xssmaze declares `reach: server` never place the
request bytes in any response: the value is read back client side out of
location.search (52 of them), localStorage, document.referrer, history.state or
a message event. 93 are DOM cases and 2 are prototype pollution. They behave
exactly like the 24 declared `reach: client`, and sitting in the denominator
they read as 95 scanner misses that no request-only engine could ever convert.
On cortex that one correction moves the DOM class from 76/174 to 76/81.

Trusting the flag and trusting its negation are the same mistake, so this
measures instead. For every exploitable endpoint declaring `reach: server` it
sends a marker through the endpoint's own delivery channel and looks for the
marker in the response. The result lands in `reach.json` next to the target's
truth.yml, and the adapter reads it.

Two rules keep the correction from flattering the scanner:

  Only `absent` is consumed. A probe that errored, timed out or had nowhere to
  put the marker scopes nothing out. The conservative half of the measurement
  is the only half that moves a denominator.

  Absence is necessary, not sufficient. The adapter scopes an endpoint out only
  when the marker provably never appeared AND the endpoint declares a
  client-side taint source. Absence alone would catch stored XSS, where the
  payload is meant to come back on a different request, and quietly delete the
  hardest class in the benchmark from the score.

No third-party imports: the control image is `docker:29-cli` plus python3 and
py3-yaml, so HTTP is `urllib` and nothing here may grow a dependency.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

# Long enough that a slow local target is not recorded as absent, short enough
# that a thousand endpoints finish. A timeout is an error, never an absence.
TIMEOUT = 8

# Digits only, and that is the whole point. The first version of this was
# `cfxZZ9mk`, chosen mixed-case on the theory that mixed case survives a target
# that lowercases its input. It does not: a transform defeats an exact match
# whichever case the marker starts in, and xssmaze has a whole `casemanip`
# family that upper-cases, swaps, title-cases and strips by case. Six endpoints
# came back "absent" while the body plainly held CfxZZ9mk, CFXzz9MK or cfx9mk.
#
# A false absence is the one error that matters here, because absence is what
# removes an endpoint from the denominator. Digits are fixed points of every
# case transform and survive strip-by-case untouched. They can collide with a
# timestamp or an id in the page, but a false *reflection* only keeps an
# endpoint in the denominator, which costs the scanner rather than flatters it.
MARKER = "479105382617"

# Where a declared delivery channel puts the marker. A channel not listed here
# is recorded as unprobed rather than guessed at, because guessing wrong writes
# an absence that scopes a real finding out of the denominator.
#   hash/fragment   never leaves the browser, so there is nothing to send
DELIVERY = {
    "query": "query",
    "json": "json",
    "path": "path",
    "form": "form",
    "post": "form",
    "header": "header",
    "cookie": "cookie",
    "referer": "referer",
    "referrer": "referer",
    "user-agent": "header",
}

# The body of the most recent probe. A single slot rather than a return value
# because `_probe`'s verdict is what every other caller wants, and threading a
# body through it would make the common path carry a megabyte it ignores.
_LAST_BODY = [None]

REFLECTS = "reflects"
ABSENT = "absent"
UNPROBED = "unprobed"
ERROR = "error"


def _client_sources(sources):
    """True when every declared taint source is read client side.

    The names are xssmaze's. A prefix match rather than a fixed set, because
    upstream adds sources and an unknown one must not be assumed server-side:
    assuming server-side keeps an endpoint in the denominator, which is the
    direction that costs the scanner rather than flatters it.
    """
    if not sources:
        return False
    client = (
        "location.", "document.referrer", "document.cookie", "document.URL",
        "document.baseURI", "localStorage", "sessionStorage", "history.state",
        "window.name", "window.opener", "indexedDB", "currentScript",
        "postMessage", "websocket-", "worker-", "sharedworker-",
        "serviceworker-", "broadcastchannel", "storage-event", "eventsource-",
        "messageport", "popstate", "hashchange", "fetch-response",
        "xhr-response",
        # Browser APIs with no server side at all. An unknown source is
        # treated as server-reaching on purpose, which is the safe default, but
        # leaving a known browser API out of this list keeps a case in the
        # denominator that no request could ever reach.
        "permissions-api", "geolocation", "clipboard", "navigator.",
        "screen.", "media-", "notification-",
    )
    return all(isinstance(s, str) and s.startswith(client) for s in sources)


def _reflected(body):
    """Whether the marker came back, allowing for the target having mangled it.

    Exact first, which with a digit marker already covers every case transform
    the target applies. Then the encodings a framework applies on the way out,
    so an entity-, percent- or base64-encoded echo counts as arrival: this
    measures whether the bytes reach the response, not whether they execute.

    Deliberately no fuzzy match. A character-dropping filter would defeat all
    of these, but inventing a subsequence rule to catch a filter no target here
    has would buy one hypothetical case at the cost of coincidental matches in
    any page full of digits, and a coincidence here writes a false absence.
    """
    if MARKER in body:
        return True
    for dec in (urllib.parse.unquote, _unentity, _unbase64_any):
        try:
            if MARKER in dec(body):
                return True
        except Exception:
            pass
    return False


def _unentity(body):
    import html
    return html.unescape(body)


def _unbase64_any(body):
    """Decode every base64-looking run in the body.

    dblenc-level3 takes a base64 parameter and replaces anything that fails to
    decode with a fixed error string, so the marker only arrives if it is sent
    encoded. `_delivery_shape` sends it that way; this is the other half, for a
    target that echoes an encoded copy.
    """
    import base64
    import re
    out = []
    for run in re.findall(r"[A-Za-z0-9+/]{8,}={0,2}", body):
        try:
            out.append(base64.b64decode(run + "=" * (-len(run) % 4),
                                        validate=False).decode("utf-8",
                                                               "replace"))
        except Exception:
            continue
    return "".join(out)


def _delivery_shape(sample):
    """Encode the marker the way the endpoint's own example value is encoded.

    An endpoint that documents `?query=YQ==` is telling us the parameter is
    base64 and that a raw value never reaches the page. Sending raw anyway
    measures the decoder, not the flow.
    """
    import base64
    if sample and len(sample) % 4 == 0 and sample.rstrip("=").isalnum():
        try:
            if base64.b64decode(sample, validate=True).decode("ascii").isprintable():
                return base64.b64encode(MARKER.encode()).decode()
        except Exception:
            pass
    return MARKER


# Classes whose exploitation spans more than one request. This probe sends a
# value and reads the reply to that same request, so it is structurally
# incapable of observing one of these: the payload is meant to come back later,
# on a different request, and absence from the immediate reply is the expected
# result rather than evidence of anything.
#
# stored-level4 and storedpat-level6 are why this is a rule and not a judgement
# call. Both declare a `fetch-response` source, because the stored value is
# served by a JSON API and pasted into innerHTML, so both looked like ordinary
# client-side flows and were scoped out. They are not: an engine that posts the
# payload and then reads the API response can see them, and scoping them out
# would have deleted two of the ten stored cases from the denominator while
# calling it a measurement.
MULTI_REQUEST_CLASSES = ("stored",)


def _multi_request(cls):
    return isinstance(cls, str) and cls in MULTI_REQUEST_CLASSES


def _first_param(params):
    """The parameter a scanner would inject into. A `#name` pseudo-param names
    a fragment, which never reaches the server."""
    for p in params or []:
        if isinstance(p, str) and p and not p.startswith("#"):
            return p
    return None


def _probe(base, ep, channel, param, timeout=TIMEOUT):
    """Send the marker and say whether it came back. Returns a verdict and the
    HTTP status, or an error string."""
    _LAST_BODY[0] = None
    url = ep.get("url") or "/"
    parts = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parts.query))
    body, headers = None, {}

    value = _delivery_shape(q.get(param))
    if channel == "path":
        # `:path` is upstream's name for "the last path segment is the
        # injection point", and every such endpoint documents it with a
        # concrete segment already in place: /path/level1/a, /edge/level2/test.
        # Replacing that segment is the only delivery those endpoints accept.
        segs = (parts.path or "/").rstrip("/").split("/")
        if len(segs) > 1:
            segs[-1] = value
        else:
            segs.append(value)
        parts = parts._replace(path="/".join(segs))
    elif channel == "query":
        q[param] = value
    elif channel == "form":
        body = urllib.parse.urlencode({param: value}).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif channel == "json":
        body = json.dumps({param: value}).encode()
        headers["Content-Type"] = "application/json"
    elif channel == "header":
        headers[param if "-" in param else "X-" + param] = value
    elif channel == "cookie":
        headers["Cookie"] = f"{param}={value}"
    elif channel == "referer":
        headers["Referer"] = f"{base}/?{param}={value}"

    target = base + urllib.parse.urlunsplit(
        ("", "", parts.path or "/", urllib.parse.urlencode(q), ""))
    method = (ep.get("method") or "GET").upper()
    if body is not None and method == "GET":
        method = "POST"

    req = urllib.request.Request(target, data=body, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            seen = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        # A 4xx or 5xx body still reflects, and an error page is where a lot of
        # reflection lives. Read it rather than discarding the measurement.
        try:
            seen = e.read().decode("utf-8", "replace")
        except OSError:
            return ERROR, f"http {e.code}, body unreadable"
        status = e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return ERROR, str(e)[:120]

    _LAST_BODY[0] = seen
    return (REFLECTS if _reflected(seen) else ABSENT), status


# A second value, same shape, used only to ask whether the endpoint reads the
# parameter at all. Must differ from MARKER in every digit so that a target
# echoing a fixed-length prefix still produces two different bodies.
CONTROL = "815372049618"


def _varies(base, ep, channel, param, timeout=TIMEOUT):
    """Does the response change when this parameter changes?

    Two probes with different values. Different bodies mean the endpoint read
    the parameter and chose not to reflect it, which is a real absence.
    Identical bodies mean the parameter was ignored and the probe is the thing
    that failed, not the target.
    """
    global MARKER
    first = _body(base, ep, channel, param, MARKER, timeout)
    second = _body(base, ep, channel, param, CONTROL, timeout)
    if first is None or second is None:
        return True  # cannot tell, so do not downgrade a recorded absence
    return first != second


def _body(base, ep, channel, param, value, timeout):
    """The raw response body for one value, or None if it could not be read."""
    global MARKER
    keep, MARKER = MARKER, value
    try:
        verdict, _ = _probe(base, ep, channel, param, timeout)
        if verdict == ERROR:
            return None
        return _LAST_BODY[0]
    finally:
        MARKER = keep


def measure(endpoints, base, timeout=TIMEOUT, progress=None):
    """Probe every exploitable endpoint declaring `reach: server`.

    Returns the dict written to reach.json. `absent` is a sorted list of ids,
    because that is the field the adapter consumes and a stable order keeps the
    committed file's diffs readable.
    """
    out = {
        "marker": MARKER,
        "measured": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base": base,
        "method": ("send the marker through the endpoint's declared delivery "
                   "channel, then look for it anywhere in the response body"),
        "absent": [],
        "reflects": [],
        "unprobed": {},
        "errors": {},
        # Which channel actually carried the marker. The map says `delivery:
        # ['body']` without saying whether the body is form encoded or JSON,
        # and an injection engine needs that to build a request the target
        # accepts. Measuring it once here beats every caller guessing, and a
        # caller that guesses `form` tests six /postmethod endpoints and all
        # six /querymethod endpoints with the payload in the wrong place.
        "channel": {},
        "client_source": [],
        "multi_request": [],
    }

    for ep in endpoints or []:
        if not isinstance(ep, dict) or not ep.get("name"):
            continue
        v = ep.get("vuln") or {}
        if not v.get("exploitable") or v.get("reach") != "server":
            continue

        name = ep["name"]
        if _multi_request(v.get("class")):
            out["multi_request"].append(name)
        elif _client_sources(v.get("sources")):
            out["client_source"].append(name)

        # Every channel the endpoint declares, not just the first. dom-level1
        # and dom-level26 declare ['fragment', 'query'], and taking [0] meant
        # both were filed unprobed on the strength of a channel that cannot be
        # probed by anyone: RFC 3986 section 3.5 leaves the fragment to the
        # user agent, so it never reaches the server at all. The query channel
        # beside it was there the whole time.
        declared = [x for x in (v.get("delivery") or []) if isinstance(x, str)]
        channels = []
        for d in declared:
            # `body` says where, not in what encoding. post-level2 and
            # postmethod-level3 both document that they want JSON and answer a
            # form encoding with the same page either way, which is exactly the
            # shape the control probe reads as "never delivered".
            for c in (("form", "json") if d == "body" else (DELIVERY.get(d),)):
                if c:
                    channels.append((d, c))
        param = _first_param(ep.get("params"))
        if not channels:
            out["unprobed"][name] = (
                f"delivery {declared or [None]} has no probe"
                + (" (a fragment never reaches the server)"
                   if any(d in ("fragment", "hash") for d in declared) else ""))
            continue
        if param is None:
            # dom-level1 declares params ['#hash'] and delivery
            # ['fragment', 'query']: it reads the whole location.href, so any
            # query name carries the marker client side and a synthetic one is
            # a fair probe of whether the server echoes the query at all.
            if any(c in ("query", "form", "json") for _d, c in channels):
                param = "q"
            else:
                out["unprobed"][name] = ("no request parameter to carry the "
                                         "marker")
                continue

        verdict, detail = ABSENT, None
        for _d, channel in channels:
            verdict, detail = _probe(base, ep, channel, param, timeout)
            if verdict == REFLECTS:
                out["channel"][name] = {"channel": channel, "param": param,
                                        "method": ep.get("method") or "GET"}
                break
        channel = channels[0][1]

        # An absence is only worth recording if the probe reached the flow, and
        # "the response did not change" is the signature of two different
        # things: a value read on the client, and a probe that never delivered.
        # The declared source tells them apart, and nothing else does.
        #
        # All sources client side: an unchanged response is the expected
        # result, so the absence stands.
        #
        # Otherwise: an unchanged response means the parameter was ignored, so
        # the endpoint wanted double base64, a JSON body or a header this does
        # not speak. Calling that absence would claim a fact about the target
        # on the strength of our own delivery bug, which is how 13 endpoints
        # with a documented reason sat in `absent` reading as measurement.
        if verdict == ABSENT and name not in out["client_source"]:
            if not _varies(base, ep, channel, param, timeout):
                out["unprobed"][name] = ("the response does not vary with this "
                                         "parameter, so the probe never "
                                         "reached the flow")
                if progress:
                    progress(name, UNPROBED)
                continue

        if verdict == ERROR:
            out["errors"][name] = detail
        else:
            out[verdict].append(name)
        if progress:
            progress(name, verdict)

    for k in ("absent", "reflects", "client_source", "multi_request"):
        out[k].sort()
    out["totals"] = {
        "probed": len(out["absent"]) + len(out["reflects"]),
        "reflects": len(out["reflects"]),
        "absent": len(out["absent"]),
        "unprobed": len(out["unprobed"]),
        "errors": len(out["errors"]),
        # The conjunction the adapter actually applies, stated here so the file
        # says what it will do rather than leaving it to be recomputed.
        "scoped_out": len(set(out["absent"]) & set(out["client_source"])),
    }
    return out


def load(target_dir):
    """Read a committed reach.json. Returns None when there is none, which is
    the normal case for every target that does not declare reach metadata."""
    if not target_dir:
        return None
    try:
        with open(os.path.join(target_dir, "reach.json")) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def unreachable(target_dir, endpoints=None):
    """The ids the adapter scopes out: measured absent AND a client-side source.

    `endpoints` lets the source half be re-read from the live map instead of the
    committed copy, so an endpoint whose sources changed upstream is judged on
    what it declares now. Falls back to the list recorded at measure time.
    """
    d = load(target_dir)
    if not d:
        return set(), None
    absent = {x for x in d.get("absent") or [] if isinstance(x, str)}
    if endpoints:
        client, multi = set(), set()
        for e in endpoints:
            if not (isinstance(e, dict) and e.get("name")):
                continue
            v = e.get("vuln") or {}
            if _multi_request(v.get("class")):
                multi.add(e["name"])
            elif _client_sources(v.get("sources")):
                client.add(e["name"])
    else:
        client = {x for x in d.get("client_source") or [] if isinstance(x, str)}
        multi = {x for x in d.get("multi_request") or [] if isinstance(x, str)}
    return (absent & client) - multi, d.get("measured")
