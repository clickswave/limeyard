# Running limeyard safely

limeyard runs deliberately vulnerable software, and our own scanner gets remote
code execution inside it on purpose. That is the point of the lab, and it is
also the threat: a Log4Shell or command-injection target doing its job means
attacker-controlled code is running in a container on your machine.

So the container is treated as a security boundary rather than a packaging
convenience, and every image is pinned to a digest we verified. This document
records what we run, why we believe it, and what is still not guaranteed.

## The honest limit, first

**A container is not a hardened security boundary against a kernel exploit.** It
is a namespace, and namespaces have had escapes. Everything below raises the
cost of an escape and removes the easy paths; none of it makes escape
impossible.

If you are running an unfamiliar target, or one that got RCE'd in a way you did
not expect, the correct isolation is a disposable VM, not a container. limeyard
is designed for a dev box you can rebuild, not a machine holding anything you
would mind losing.

Two rules that are not negotiable:

- **Never expose this to a network.** Every published port binds `127.0.0.1`,
  and `./lime audit` fails if that changes.
- **Never run it on a machine with credentials that matter.** Docker socket
  access is root on the host, and the lab needs the socket to function.

## What actually runs here

Every image, its publisher, and why we trust it. Verified 2026-09-08 against the
Docker Hub and GHCR APIs.

### Docker Official Images

`redis`, `mongo`, `memcached`, `registry`, `postgres`, `mysql`, `nginx`,
`mariadb`, `python`. Built and maintained by Docker's official images programme
from published Dockerfiles, billions of pulls each. This is the strongest
provenance available and it covers most of the supporting infrastructure.

### Project organisation accounts

| Image | Publisher | Pulls | Last push |
|---|---|---|---|
| `owasp/modsecurity-crs` | OWASP Core Rule Set project | 6.5M | 2026-08-13 |
| `crapi/*` (5 images) | OWASP crAPI project | ~1.1M each | 2025-09-22 |
| `webgoat/webgoat` | OWASP WebGoat project | 462k | 2025-03-11 |
| `traefik/whoami` | Traefik Labs | 41M | 2026-07-29 |
| `prom/prometheus` | Prometheus project | 2.0B | 2026-08-18 |
| `internetsystemsconsortium/bind9` | ISC, who write BIND | 4.7M | 2026-08-19 |
| `axllent/mailpit` | the author of Mailpit | 217M | 2026-09-05 |

### Author-published, identifiable maintainers

Each is published by the person or project that wrote the software, under their
own namespace, with a public identity attached.

| Image | Publisher | Pulls | Last push |
|---|---|---|---|
| `bkimminich/juice-shop` | Bjoern Kimminich, OWASP Juice Shop lead | 87M | 2026-08-11 |
| `ghcr.io/digininja/dvwa` | Robin Wood, DVWA author | GHCR | current |
| `ghcr.io/christophetd/log4shell-vulnerable-app` | Christophe Tafani-Dereeper, Datadog | GHCR | current |
| `dolevf/dvga` | Dolev Farhi, DVGA author | 982k | 2025-05-24 |
| `erev0s/vampi` | erev0s, VAmPI author | 137k | 2026-04-07 |
| `sasanlabs/owasp-vulnerableapp` | SasanLabs, OWASP VulnerableApp | 92k | 2026-09-08 |

### The two weak links, named

**`raesene/bwapp`** is the weakest thing in the lab. Rory McCune is a
well-known and reputable security engineer, so the packager is not the concern.
The problems are that the image was **last rebuilt 2022-05-06**, its repo is
**archived**, and it declares **no licence**. A four-year-old PHP and MySQL
image carries four years of unpatched CVEs in its own base layers. It is pinned
by digest, capability-dropped and memory-capped like everything else, and it is
the first target to drop if you want to reduce exposure.

**`delfer/alpine-ftp-server`** is a single individual's image (5.3M pulls, last
push 2025-03-01). Widely used, but one person's account. It is only reachable
on the internal lab network and publishes no host port.

Also worth knowing: crAPI ships `mongo:4.4`, which is past end of life. It is
`heavy` and excluded from `--all`, so it does not run unless you ask for it.

### Nothing is vendored

limeyard contains no third-party source code. Targets are official images pulled
by digest, or repos fetched at runtime into a gitignored `src/`. Only `mirage`
and the estate configs are ours, and mirage builds from `python:3.12-alpine`
with no dependencies at all.

## Supply chain

**Every image is pinned by digest**, not by tag. A floating `:latest` is a
standing invitation: a compromised publisher account or an abandoned repo
changing hands silently changes what you run. Pins are the digest that was
actually pulled and tested on this machine.

```sh
./lime pin           # report drift between the compose files and the registry
./lime pin --apply   # re-pin deliberately, as a reviewable change
```

Re-pinning is a deliberate act that shows up in a diff. `./lime audit` fails on
any unpinned image.

## Container hardening

Applied to every service in every target and scenario, and enforced by
`./lime audit`:

| Control | What it stops |
|---|---|
| `security_opt: no-new-privileges:true` | a setuid binary inside the container escalating to root |
| `cap_drop: ALL` | the default capability set, most of which no web app needs |
| `cap_add`, minimum per image | capabilities added back one at a time, only where the image genuinely needs them |
| `pids_limit: 512` | a fork bomb staying inside its own container |
| `mem_limit` | a DoS target (dvga has query amplification by design) taking the host with it |
| private `internal: true` network for database tiers | a popped database reaching the internet |
| `127.0.0.1` binds only | anything on your network reaching the lab |

Capabilities are per image because dropping them blindly breaks things, and a
broken target is a target someone will disable the hardening on. Images whose
entrypoint starts as root and drops to a service user (`setpriv`, `su-exec`,
`gosu`) need `SETUID`/`SETGID` or they exit 127 on boot; Apache and nginx also
need `NET_BIND_SERVICE`, `CHOWN` and `DAC_OVERRIDE`. Everything else runs with
no capabilities at all.

`./lime audit` also hard-fails on `privileged`, `network_mode: host`, host
`pid`/`ipc`, any Docker socket mount in a target, and dangerous `cap_add`
(`SYS_ADMIN`, `SYS_PTRACE`, `SYS_MODULE`, `NET_ADMIN`, `NET_RAW`).

All 14 targets and the estate scenario were started under this profile and
verified serving traffic, so the hardening is known not to be theatre.

## The control plane is the sharpest edge

`limed` mounts `/var/run/docker.sock`, which is **root-equivalent on the host**.
It has to: driving each target as its own compose project is what it does. It
also has to share a network with the targets, because setup hooks curl them by
service name.

Docker bridges are bidirectional, so "limed can reach targets but targets cannot
reach limed" is not expressible in compose. Reachability is therefore made
insufficient instead: **limed requires a shared secret** (`X-Lime-Token`) on
every endpoint except `/api/health`, compared in constant time. A target that
gets popped can open a socket to limed and learn nothing.

Generate one before first run, and `./lime audit` fails while it is unset:

```sh
echo "LIME_TOKEN=$(openssl rand -hex 24)" >> .env
```

The token lives server-side only. The UI holds it in its Node process and proxies
browser requests; it is never sent to the browser.

## What is still not covered

Stated plainly, so nobody assumes otherwise:

- **Kernel escapes.** Nothing here defends against a container breakout via a
  kernel bug. Use a VM if that is in your threat model.
- **No seccomp or AppArmor profiles beyond Docker's defaults.** Docker's default
  seccomp profile is applied and is reasonable. We have not written tighter
  per-target profiles.
- **No user namespace remapping.** Enabling `userns-remap` on the daemon would
  mean root in a container is not root on the host. It is a daemon-wide setting
  with real friction, so it is a deliberate omission rather than an oversight.
- **Egress is not blocked on `lime-web`.** Targets that need it have
  `egress: true` in their manifest (log4shell needs OAST callbacks), but the
  bridge does not currently enforce the distinction. Database tiers are on
  `internal: true` networks and genuinely cannot reach out.
- **APK fixtures are not sandboxed by any of this.** `androgoat` is an Android
  artifact you install on a device or emulator. Its trust story is the device's,
  not this lab's.

## Reporting

This lab is deliberately vulnerable, so vulnerabilities in the targets are not
findings. What is worth reporting: anything that lets a target escape its
container, reach the host, or drive limed without the token. Those are real
bugs in limeyard.

Report those privately, at
<https://github.com/clickswave/limeyard/security/advisories/new>, not as an
issue. Include what you ran and what you got; a container id and a shell prompt
on the host says more than a description of one.

Everything else, including a target that will not start and an answer key that
is wrong, belongs in the issue tracker where other people can see it.
