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

```sh
cp .env.example .env
echo "LIMEYARD_DIR=$PWD"                 >> .env
echo "LIME_TOKEN=$(openssl rand -hex 24)" >> .env   # required, see SECURITY.md
docker compose up -d          # control plane + UI on http://127.0.0.1:7000
./lime start --all            # every light target
./lime scenario-up estate     # the network estate: DNS, vhosts, services
./lime credits                # who wrote each target, and under what licence
./lime doctor                 # environment, attribution and disk checks
./lime doctor --fix           # apply every check's automatic remedy, then re-check
./lime audit                  # container hardening + supply chain invariants
./lime pin                    # report image drift against the registry
```

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

limeyard runs other people's work. Every target below was built by
someone else unless it says Clickswave.

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
| mirage | Clickswave | proprietary | - |

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

### service

| target | author | licence | source |
|---|---|---|---|
| Open services | Clickswave (composition of upstream official images) | mixed, per-image | - |

### web

| target | author | licence | source |
|---|---|---|---|
| bWAPP | Malik Mesellem (pkg: Rory McCune (raesene)) | none declared | [repo](https://github.com/raesene/bWAPP) |
| DVWA | Robin Wood (digininja) | GPL-3.0 | [repo](https://github.com/digininja/DVWA) |
| FaultLine ISP | Clickswave | proprietary | [repo](https://github.com/clickswave/faultline) |
| OWASP Juice Shop | Bjoern Kimminich (OWASP Juice Shop project) | MIT | [repo](https://github.com/juice-shop/juice-shop) |
| OWASP Mutillidae II | Jeremy Druin (webpwnized), OWASP Mutillidae II | GPL-3.0 | [repo](https://github.com/webpwnized/mutillidae) |
| OWASP RailsGoat | OWASP RailsGoat project | MIT | [repo](https://github.com/OWASP/railsgoat) |
| OWASP WebGoat + WebWolf | OWASP WebGoat project | GPL-2.0 | [repo](https://github.com/WebGoat/WebGoat) |

