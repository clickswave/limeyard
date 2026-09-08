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
  url: http://vulnerableapp:9090/scanner/dast
  format: vulnerableapp-dast # vulnerableapp-dast | owasp-benchmark-csv |
                             # xssmaze-solutions | wavsep-paths | crawl-maze
```

## scope

The field that keeps the accounting honest.

- `black-box` counts toward recall. An unauthenticated automated scanner is
  expected to find it.
- `authed` counts toward recall only when the run seeded credentials for this
  target. Skipped otherwise, never counted as a miss.
- `out-of-scope` never counts. It documents a real vulnerability that needs a
  human or a step a scanner is not meant to take: brute force, OTP flows,
  business logic, lesson progression, code-level issues with no black-box
  oracle. It is recorded so nobody re-litigates it every quarter.

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
ssrf  ssti  xxe  crlf  open-redirect  deserialization  race  smuggling
cache-poisoning  proto-pollution  jwt  mass-assignment  bola  bfla  bopla
excessive-exposure  cors  auth-bypass  session  info-disclosure  default-creds
exposure  panel  tech  cve  misconfig  dos
```

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
