# limeyard

A security testing lab. A fleet of deliberately vulnerable targets, a routable
network estate with authoritative DNS for asset discovery to enumerate, a
machine-readable answer key per target, and a control panel to drive it all.

> **Everything here is deliberately vulnerable. Local testing only.** Do not
> expose it to the internet or an untrusted network. Published ports bind to
> `127.0.0.1`; lab targets bind to nothing at all.
>
> Our own scanner gets RCE inside these containers on purpose, so the container
> is treated as a security boundary: every image is pinned by digest, every
> service drops all capabilities and adds back a minimum, and `./lime audit`
> enforces it. Read [SECURITY.md](SECURITY.md) before first run, including the
> part about what container isolation does not cover.

[![The limeyard control panel, listing every target with its kind, state, address and upstream](https://raw.githubusercontent.com/clickswave/limeyard/main/docs/panel.png)](#control-panel)

The control panel on http://127.0.0.1:7000, showing the lab as it runs.

limeyard was `vuln_apps`. It was renamed because it stopped being a folder of
applications: it now holds bare services, a DNS zone, a WAF pair, a precision
target and APK fixtures, none of which are apps.

## Why it changed

The old fleet scored 9 of 9, zero misses, zero false positives. A benchmark that
cannot fail cannot detect a regression. Three things were wrong structurally:

- **Three of five engines had no ground truth.** Every app was `127.0.0.1:70xx`,
  so subdomain enumeration had nothing to enumerate, port scanning was handed
  its answer, and service fingerprinting never saw a non-HTTP daemon.
- **11 of 101 detection templates had ever fired.** The other 90 shipped with no
  live target of any kind.
- **Nothing measured precision.** Every target was genuinely vulnerable, so
  "zero false positives" was unfalsifiable.

## Quick start

You need Docker (with the compose plugin) and git. Nothing else.

```sh
curl -fsSL https://raw.githubusercontent.com/clickswave/limeyard/main/install.sh | bash
```

That clones the lab into `./limeyard`, writes its `.env` with a fresh API
token, builds and starts the control plane, then asks what to run. Before
anything starts it shows what the selection costs, measured idle on the
reference box, against what your machine has free:

```
This selection, idle, on the box it was measured on:
  17 targets, 1 scenarios, 45 containers
  RAM  about 2.9 GB resident  (host has 22.4 GB available)
  disk about 11.0 GB of images to pull  (host has 111 GB free)
  CPU  near idle once up (3% of one core); pulling and first boots are the busy part
Start it? [y/N]
```

Non-interactive: `curl ... | bash -s -- --light --yes` (or `--all`,
`--none`, `--pick dvwa,juice-shop,estate`). Put the checkout elsewhere with
`LIMEYARD_DIR=/path`.

The panel is then at http://127.0.0.1:7000, and the same things by hand:

```sh
./lime setup                  # the wizard again, any time
./lime start --all            # every light target
./lime start crapi --heavy    # a heavy one, explicitly
./lime scenario-up estate     # the network estate: DNS, vhosts, services
./lime status                 # what is up
./lime stop --all --heavy     # everything down; images and volumes stay
./lime credits                # who wrote each target, and under what licence
./lime doctor                 # environment, attribution and disk checks
./lime doctor --fix           # apply every check's automatic remedy, then re-check
./lime audit                  # container hardening + supply chain invariants
./lime pin                    # report image drift against the registry
```

By hand, without the installer:

```sh
git clone https://github.com/clickswave/limeyard && cd limeyard
cp .env.example .env
echo "LIMEYARD_DIR=$PWD"                 >> .env
echo "LIME_TOKEN=$(openssl rand -hex 24)" >> .env   # required, see SECURITY.md
docker compose up -d --build  # control plane + UI on http://127.0.0.1:7000
./lime setup
```

Every manifest carries a measured `resources` block (containers, idle RAM,
image disk, idle CPU). The wizard, the panel's selection strip and each
target's page sum from it, so the estimate is the same everywhere.

## Branches

Two, and only two.

- **`main`** is what the installer clones and what you get if you do nothing.
  It moves by pull request, never by a direct push.
- **`dev`** is the default branch and where work lands. Open pull requests
  against it.

## Concepts

| | |
|---|---|
| **target** | one thing under test, of a declared `kind`. Owns a compose file, optional setup, and its own answer key. Runs as its own isolated compose project, so two targets using Postgres never share one |
| **scenario** | several targets wired into a network topology with authoritative DNS. What asset discovery is scored against |
| **truth** | the machine-readable answer key. See [truth/schema.md](truth/schema.md) |
| **doctor** | one list of checks with a verdict each: environment, attribution, supply chain, hardening. Checks with an unambiguous remedy carry a one-click fix in the panel (`/doctor`) and `--fix` on the CLI: create networks, reclaim disk, pin images, fetch sources, re-verify running targets, rewrite off-loopback binds. Attribution, port clashes and hardening need a person |

Kinds: `web api bench cve service estate edge control mobile`.

## Layout

```
targets/<kind>/<slug>/     target.yml, compose.yml, setup.sh, truth.yml
scenarios/<slug>/          scenario.yml, compose.yml, zones/
control/limed/             the daemon: CLI + HTTP API + scorer
control/ui/                the SvelteKit control panel
truth/                     the contract, and dated scorecards
```

## Control panel

`docker compose up -d` starts two containers and nothing else: `limeyard_control`
(the limed daemon, holding the Docker socket) and `limeyard_ui` (the SvelteKit
panel). Both bind loopback only. The panel is at http://127.0.0.1:7000 and the
raw API at http://127.0.0.1:7099. Both need `.env`, and `LIME_TOKEN` in it is
mandatory: the panel holds the token server-side and the browser never sees it.

| page | what it is for |
|---|---|
| **Targets** | every target, filter by kind and state, sort, multi-select with Start, Stop, Restart. Click a row for the target |
| **Target** | facts (address, credentials, stack, upstream, verification, image digests), the live log, and the answer key with its negatives |
| **Scenarios** | the estate: resolver, zones, subnet, and a host table with per-container state. Bring up, bring down, restart |
| **Scorecard** | the latest run with deltas, per-class and per-target coverage, missed ids, a history you can view, and a two-run diff |
| **Ports** | what binds on localhost, and what only exists on the lab bridge |
| **Doctor** | one list of checks with a verdict each. Fix and Fix all show the exact commands and file edits first, computed from the lab as it is, and run them on confirmation. A fix that leaves its check failing says so |
| **Credits** | who wrote each target and under what licence |

The panel updates itself: limed streams state transitions over SSE, so a
target started from the CLI shows up without a refresh. The header carries
the host's CPU, RAM and free disk from the same stream, coloured only when
they are worth noticing. Every table sorts by
clicking a column header; a second click flips the direction.

After a change to the panel or the daemon, rebuild the pair:

```sh
docker compose up -d --build
```

To work on the panel against a running daemon without rebuilding the image:

```sh
cd control/ui && npm install
LIMED_URL=http://127.0.0.1:7099 LIME_TOKEN=<from .env> npm run dev   # :7000
```

### API

Every call except `/api/health` needs `X-Lime-Token`.

```
GET  /api/targets                    list, with state and attribution
GET  /api/targets/<slug>             plus truth, images, lab addresses
GET  /api/targets/<slug>/logs        SSE, docker compose logs -f
POST /api/targets/<slug>/<action>    start | stop | restart | pull | setup
POST /api/targets/bulk               {action, slugs}: a pool of three, per-slug refusals
GET  /api/scenarios                  with per-host container state
POST /api/scenarios/<slug>/<action>  up | down | restart
GET  /api/scorecards                 newest first, by_class carries false positives
GET  /api/scorecards/<id>            one card
POST /api/score                      {tool, findings, save?, targets?}
GET  /api/doctor                     checks with verdict, reason, value, items, fix
POST /api/doctor/fix                 {ids}: those checks, or every fixable one when empty
GET  /api/ports  /api/credits  /api/truth  /api/status
GET  /api/events                     SSE: state, scenario, tick
```

## Networks

Three tiers, because one was the original problem.

- **`lime-web`** bridge. Web and API targets, published on `127.0.0.1:70xx`.
- **`lime-lab`** bridge, `10.66.0.0/16`, static IPs, no host binding. A scanner
  joins this network as a container and sees a real subnet with real hosts and
  real ports instead of a loopback port list.
- **`lime-edge`** the WAF tier, with the origin reachable but absent from DNS.

DNS is authoritative BIND on `.test` zones (RFC 6761 reserves it). Docker network
aliases are deliberately not the source of truth: they never appear in a zone
transfer, and would make the topology disagree with the answer key.

## Ports

| range | use |
|---|---|
| 7000 | the UI |
| 7099 | limed API |
| 7001-7099 | web and api targets |
| 7100-7199 | benchmark suites |
| 7200-7299 | CVE labs |
| 7300-7399 | edge and control targets |
| 5353 | lab DNS |
| none | service and estate targets, `lime-lab` addresses only |

## Scoring

Every target ships a `truth.yml`. The scorer turns findings into precision,
recall and F1, per target and per class:

```sh
curl -s -XPOST localhost:7099/api/score -H 'Content-Type: application/json' \
  -d '{"tool":"crossfyre","save":true,"findings":[...]}'
```

Three things are counted, not one. **Recall**: did we find what is there.
**Precision**: did we avoid reporting what is not, measured against the
`negative` entries every answer key carries. **Scope**: what we correctly did
not attempt, recorded so nobody re-litigates it every quarter.

The `mirage` target exists only for the second one. Nothing in it is vulnerable
and everything in it looks like it is, so any finding against it is a false
positive by construction.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) has the whole of it: what a contribution
usually is, the invariants `./lime audit` enforces, and why a correction to an
answer key is worth more here than a new feature. The short version of the
rules is below. Everyone taking part is held to the
[code of conduct](CODE_OF_CONDUCT.md).

## Adding a target

```
targets/<kind>/<slug>/
  target.yml    manifest, including a REQUIRED upstream block
  compose.yml   the containers. 127.0.0.1 binds only
  setup.sh      optional one-time init, run after start
  truth.yml     the answer key
```

Rules that keep the lab clean:

- Bind only the target port, to `127.0.0.1`.
- Single-container targets join `[lime-web]` only. Do not add a per-project
  network: too many networks and Docker runs out of address pool.
- Targets with a database join `[default, lime-web]` and put the database on
  `[default]` only. Each target gets its own database service and volume.
- Targets that exist to be discovered rather than browsed join `[lime-lab]` with
  a static IP and publish no host port.
- **`upstream` is mandatory.** `lime doctor` fails a target without it and the
  manager refuses to register one. See below.
- limeyard vendors no third-party source. Put `repo:` and `compose:` in the
  manifest and the source is fetched at runtime into `<target>/src` instead.
- Record what it costs. Start it, let it settle, and `./lime measure <slug>`
  prints the `resources` block to paste in. The installer and the panel add
  these up to warn someone before they start it, so a guess here is a lie there.

## Trust and isolation

Targets are other people's deliberately vulnerable software, so provenance is
recorded rather than assumed, and the runtime is constrained rather than
trusted. [SECURITY.md](SECURITY.md) has the full picture; the short version:

- Every image is **pinned by digest**, not a floating tag, to the digest that
  was pulled and tested here. `./lime pin` reports drift.
- Publishers are documented per image: Docker Official Images, project
  organisation accounts (OWASP, ISC, Traefik, Prometheus), or the author's own
  namespace. The two weakest links, `raesene/bwapp` (archived, last rebuilt
  2022, no licence) and `delfer/alpine-ftp-server` (one individual), are named
  as such.
- Every service runs with `no-new-privileges`, `cap_drop: ALL` plus a minimum
  per-image `cap_add`, a pid ceiling and a memory ceiling. Database tiers sit on
  `internal: true` networks with no route out.
- `limed` holds the Docker socket, which is root on the host, so it requires a
  shared secret on every call. A popped target can reach it and learn nothing.
- `./lime audit` fails on `privileged`, host networking, a socket mount in a
  target, an off-loopback bind, an unpinned image or a missing token.

Nothing here defends against a kernel-level container escape. For that, use a
disposable VM.

## Attribution

Nearly everything here was written by someone else, and several targets declare
no licence at all. So crediting the author is a hard gate, not a convention:

- `target.yml` carries a required `upstream` block: author, repo, licence,
  and the date we last verified it builds. `packager` records the person who
  containerised something when that differs from who wrote it.
- Every dashboard card shows the author under the target name, linked to the
  source, with the licence beside it. A licence of `none declared` renders as a
  warning, which is also the do-not-redistribute signal.
- Each target's detail view opens with a credit block, above the vulnerability
  list, with our answer key clearly separated from upstream's own docs.
- `/credits` in the UI and `./lime credits` list every target, author and
  licence. `./lime credits --markdown` regenerates the section below.

## Credits

<!-- generated by `lime credits --markdown`; do not edit by hand -->

limeyard runs other people's work. Every target and scenario below was
built by someone else unless it says Clickswave.

### api

| target | author | licence | source |
|---|---|---|---|
| OWASP crAPI | OWASP crAPI project | Apache-2.0 | [repo](https://github.com/OWASP/crAPI) |
| DVGA | Dolev Farhi | MIT | [repo](https://github.com/dolevf/Damn-Vulnerable-GraphQL-Application) |
| VAmPI | erev0s | MIT | [repo](https://github.com/erev0s/VAmPI) |

### bench

| target | author | licence | source |
|---|---|---|---|
| Crawlground | ZAP project (zaproxy) | Apache-2.0 | [repo](https://github.com/zaproxy/crawlground) |
| Security Crawl Maze | Google | Apache-2.0 | [repo](https://github.com/google/security-crawl-maze) |
| OWASP VulnerableApp | SasanLabs (OWASP VulnerableApp project) | Apache-2.0 | [repo](https://github.com/SasanLabs/VulnerableApp) |
| XSSMaze | hahwul (author of dalfox) | MIT | [repo](https://github.com/hahwul/xssmaze) |

### control

| target | author | licence | source |
|---|---|---|---|
| mirage | Clickswave | MIT | [repo](https://github.com/clickswave/mirage) |

### cve

| target | author | licence | source |
|---|---|---|---|
| Log4Shell lab | Christophe Tafani-Dereeper (christophetd) | Apache-2.0 | [repo](https://github.com/christophetd/log4shell-vulnerable-app) |

### edge

| target | author | licence | source |
|---|---|---|---|
| ModSecurity CRS pair | OWASP Core Rule Set project (coreruleset) | Apache-2.0 | [repo](https://github.com/coreruleset/modsecurity-crs-docker) |

### mobile

| target | author | licence | source |
|---|---|---|---|
| AndroGoat | Satish Patnayak | none declared | [repo](https://github.com/satishpatnayak/AndroGoat) |

### scenario

| scenario | author | licence | source |
|---|---|---|---|
| estate | Clickswave | MIT | - |

### service

| target | author | licence | source |
|---|---|---|---|
| Open services | Clickswave (composition of upstream official images) | mixed, per-image | - |

### web

| target | author | licence | source |
|---|---|---|---|
| bWAPP | Malik Mesellem (pkg: Rory McCune (raesene)) | none declared | [repo](https://github.com/raesene/bWAPP) |
| DVWA | Robin Wood (digininja) | GPL-3.0 | [repo](https://github.com/digininja/DVWA) |
| FaultLine ISP | Clickswave | MIT | [repo](https://github.com/clickswave/faultline) |
| OWASP Juice Shop | Bjoern Kimminich (OWASP Juice Shop project) | MIT | [repo](https://github.com/juice-shop/juice-shop) |
| OWASP Mutillidae II | Jeremy Druin (webpwnized), OWASP Mutillidae II | GPL-3.0 | [repo](https://github.com/webpwnized/mutillidae) |
| OWASP RailsGoat | OWASP RailsGoat project | MIT | [repo](https://github.com/OWASP/railsgoat) |
| OWASP WebGoat + WebWolf | OWASP WebGoat project | GPL-2.0 | [repo](https://github.com/WebGoat/WebGoat) |
