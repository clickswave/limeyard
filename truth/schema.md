# truth.yml

The machine-readable answer key. Every target ships one. The scorer reads them
all and turns a scanner's findings into precision, recall and F1, per target and
per vulnerability class.

`vulns/*.md` and each target's `README.md` stay as the human-readable catalog.
`truth.yml` is the half a machine reads. When they disagree, the markdown is the
narrative and `truth.yml` is the contract.

## Shape

```yaml
target: dvwa                 # must match the slug
scoring: findings            # findings | endpoints | hosts | ports | assets | crawl

expected:                    # things a scanner SHOULD report
  - id: DV1                  # stable id, referenced by scorecards forever
    class: sqli              # normalised class, see the list below
    severity: high
    scope: black-box         # black-box | authed | out-of-scope
    where:
      method: GET
      path: /vulnerabilities/sqli/
      param: id
      in: query              # query | body | header | cookie | path
    confirm: error-based     # how it is provable; free text
    note: optional prose

negative:                    # things a scanner MUST NOT report.
  - id: DV-N1                # reporting one of these is a false positive
    where: {method: GET, path: /safe.php, param: q}
    note: reflects input without executing it

external:                    # for suites that serve their own ground truth
  type: http
  url: http://xssmaze:3000/map/json
  format: xssmaze-map        # see the table below
  file: path/in/src.json     # optional: a committed copy, preferred over HTTP
  solutions: http://...      # optional: a secondary source, see xssmaze-map
```

## external

A target that already publishes its own answer key should not have it copied
into a truth.yml, because the copy drifts. `external` names where it lives and
`control/limed/external.py` resolves it into ordinary `expected` / `negative`
entries, which the scorer then handles exactly like a hand-written key.

A committed `file` is preferred over `url`, because it resolves with the lab
cold and it is the same bytes the target would serve.

Two kinds, and the difference decides who scores:

- **answer key.** The target says what *should* be found. Resolves into
  `expected` and `negative`, scored locally. `crawl-maze`, `xssmaze-map`.
- **self scored.** The target says what *was* found, because it hands out
  markers linked from nowhere else and records who reached them. There is
  nothing to match locally and the verdict is imported. `crawlground`.

| format | adapter | notes |
|---|---|---|
| `crawl-maze` | yes | 91 paths, flat list, resolves from the committed copy |
| `xssmaze-map` | yes | 1064 endpoints; `exploitable:false` becomes a negative, `reach: client` and a measured `reach.json` are scoped out, `solutions` fills `confirm` |
| `crawlground` | no | self scored, needs the POST /set-tool handshake |
| `vulnerableapp-dast` | yes | 155 rows over 38 types; `variant: SECURE` becomes a negative, and the grader at /scanner/benchmark is for a submit-and-compare rather than resolution |
| `owasp-benchmark-csv` | no | no target uses it yet |
| `wavsep-paths` | no | no target uses it yet |

A declared format with no adapter is reported as unresolved on the scorecard,
never as a target with nothing to find.

An `expected` or `negative` entry written into a truth.yml that also declares
`external` is kept, and wins on id. Upstream's key is upstream's: a real
vulnerability it does not document cannot be added to it, and a truth.yml is
the only place that finding can live. Four reflected XSS on VulnerableApp's
ErrorBasedSQLInjection levels are there for that reason. Resolution used to
hand back only what the adapter built, and every caller assigned it straight
over `expected`, so a hand-written entry beside an external block vanished
without saying so.

## reach.json

A target that tells the lab, per endpoint, whether a flow touches an HTTP
response is handing over the one fact that decides whether a request-only
scanner had anything to see. Only xssmaze does, with a `reach` of server or
client, and the adapter scopes the client ones out rather than counting them as
misses.

Measured 2026-10-01T23:25Z, the flag is wrong in one direction: 95 endpoints
xssmaze declares `reach: server` never put the request bytes in any response.
The value is read back on the client out of `location.search` (52 of them),
`localStorage`, `document.referrer`, `history.state` or a message event. 93 are
DOM cases and 2 are prototype pollution. They behave exactly like the 24
declared `reach: client`, and left in the denominator they read as 95 scanner
misses that no request-only engine could convert. On cortex that one
correction moves the DOM class from 76/174 to 76/81.

Trusting the flag and trusting its negation are the same mistake, so `lime
reach <target> --write` measures it and commits the result to `reach.json`
beside the truth. The adapter reads it, the scorecard reports
`reach_scoped_out` and the date, and the file is reviewable as data instead of
the correction being asserted in a note.

Three rules stop the correction from flattering the scanner, and all three
exist because the first version of the probe got it wrong:

- **Only `absent` is consumed.** A probe that errored or had nowhere to put its
  marker scopes nothing out.
- **Absence is checked against a control.** For an endpoint with a server-side
  source, an unchanged response means the parameter was ignored and the probe
  never arrived, so it is recorded `unprobed`. Thirteen endpoints that wanted
  double base64, a JSON body or an `Accept` header sat in `absent` reading as
  measurement. Eight are still unprobed for that reason and stay in the
  denominator, which costs the scanner rather than flatters it.
- **Absence is necessary, not sufficient.** An endpoint is scoped out only when
  the marker provably never appeared *and* every declared taint source is read
  client side, *and* its class is not one whose exploitation spans requests.
  Stored XSS is the case that matters: the payload is meant to come back on a
  later request, so absence from the immediate reply is the expected result.
  `stored-level4` and `storedpat-level6` declare a `fetch-response` source and
  were scoped out by an earlier version of this, which would have deleted two
  of the ten stored cases while calling it a measurement.

Every channel an endpoint declares is tried, not the first. `dom-level1` and
`dom-level26` declare `['fragment', 'query']`, and taking the first filed both
unprobed on the strength of a channel nobody can probe: RFC 3986 section 3.5
leaves the fragment to the user agent, so it never reaches the server at all.
A `:path` parameter means the last path segment is the injection point and is
probed by replacing it, which is how six endpoints moved out of `unprobed` and
proved they do reflect.

The marker is digits only. A mixed-case marker was tried first, on the theory
that mixed case survives a target that lowercases input. It does not: a
transform defeats an exact match whichever case it starts from, and xssmaze has
a `casemanip` family that upper-cases, swaps and strips by case. Six endpoints
came back absent while the body plainly held the marker. Digits are fixed
points of every one of those transforms.

## scope

The field that keeps the accounting honest.

- `black-box` counts toward recall. An unauthenticated automated scanner is
  expected to find it.
- `authed` counts toward recall only when the run seeded credentials for this
  target. Skipped otherwise, never counted as a miss.

  A label is only worth something if it is true, and six of them were not.
  DVWA's DV1 to DV3 and bWAPP's BW1, BW2 and BW4 all said `black-box` and all
  six answer a redirect to /login.php with no credentials, so an
  unauthenticated run was scored six misses for endpoints it never saw.
  `lime gated [target]` is the lint for that: it requests each entry's path
  with no credentials and a browser Accept header, and names any entry the
  truth calls black-box that the application will not serve. Evidence goes to
  `gated.json` beside the truth.

  It is a lint and not a resolver on purpose. `scope` is this lab's own
  judgement about what a scanner is expected to do, unlike `reach.json` which
  records a fact about the target, so the label stays hand-written and a
  person moves it and says why. Three signals count: a 401 or 403, a response
  carrying a password input where the path asked for was not itself a login
  path, and a redirect that landed somewhere login-shaped. A body that merely
  mentions "login" does not, because every application has a login link in its
  navigation and counting that would relabel the whole fleet.
- `out-of-scope` never counts. It documents a real vulnerability that needs a
  human or a step a scanner is not meant to take: brute force, OTP flows,
  business logic, lesson progression, code-level issues with no black-box
  oracle. It is recorded so nobody re-litigates it every quarter. A flow that
  never touches an HTTP response is this case, whether the target declares it
  or `reach.json` measures it.

### `in`, and what an authorization finding reports

`in` names where the input sits: query, body, header, cookie, path, fragment.
It is advisory, so a mismatch flags rather than fails, and one mismatch is
expected often enough to be worth writing down.

An authorization probe that compares what two identities get back from one
endpoint reports `endpoint`, because that is what it proved: the endpoint is
the object and it is not scoped to its owner. The truth entry for the same
case says `path` or `query`, because that is where the object's id lives,
which is a fact about the vulnerability rather than about the measurement.
Both are right and `endpoint` is the less specific one, so it no longer raises
a flag. crAPI's CR1 carried one on every run and it was noise.

A probe that did substitute an id into the path says `path`, because there the
location is the evidence.

## negative

The reason limeyard exists. A fleet where every target is vulnerable can only
measure recall, and a recall-only score is how a scanner ends up shipping noisy
heuristics.

A `negative` entry is a place where the correct behaviour is silence. A finding
whose class and location match a `negative` entry is a false positive, counted
and named in the scorecard. Targets that ship a hardened twin (OWASP
VulnerableApp's SECURE levels, WAVSEP's FalsePositive cases, mirage in its
entirety) express that twin here.

## classes

Normalised so the scorer can match across targets regardless of what the scanner
calls them. Extend deliberately, not per-target.

```
sqli  nosqli  xss-reflected  xss-stored  xss-dom  cmdi  lfi  traversal  rfi
ssrf  ssti  csti  xxe  crlf  open-redirect  deserialization  race  smuggling
cache-poisoning  proto-pollution  jwt  mass-assignment  bola  bfla  bopla
excessive-exposure  cors  auth-bypass  session  info-disclosure  default-creds
exposure  panel  tech  cve  misconfig  dos
```

`csti` is separate from `ssti` on purpose, and was added because folding it in
was wrong. xssmaze's five `csti` endpoints are AngularJS and Vue `{{ }}`
expressions evaluated in the browser; the adapter mapped them to `ssti`, which
put a row reading "ssti 0/5" on every scorecard for a target that has no
server-side template injection in it at all, and meant an engine would have had
to report the wrong class to score. The impact is XSS and the oracle is a
template evaluating, so it shares neither class's detection path.

## matching

A finding matches an `expected` entry when the class matches and the location
matches. Location matching is deliberately loose on the parts scanners disagree
about and strict on the parts they should not:

- `path` must match exactly after normalising trailing slashes.
- `param` must match exactly when the entry names one. An entry with no `param`
  matches any finding on that path.
- `method` must match when the entry names one.
- `in` is advisory. A scanner reporting the right param in the wrong location
  still matches, but the scorecard flags it, because header and cookie injection
  points are where scanners silently score zero.

Unmatched findings are partitioned: those hitting a `negative` entry are false
positives, the rest are `unmatched` and listed so a genuine finding we failed to
document gets promoted into `expected` rather than silently punished.
