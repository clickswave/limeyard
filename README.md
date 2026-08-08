# vuln_apps

A fleet of intentionally-vulnerable apps to point security tooling at (crossfyre,
Burp, ZAP, nuclei, and so on). This folder holds **no app source**, just skeleton
definitions and a small manager. Each app runs as its own isolated container
stack, so nothing clashes.

> **Everything here is deliberately vulnerable. Local testing only.** Do not
> expose these to the internet or an untrusted network. All ports bind to
> `127.0.0.1`.

## How it works

- `docker compose up` starts one container: **`vuln_apps_manager`** (the control
  plane). It does not start any vuln app by itself.
- You drive the fleet through the manager. Each app is defined by a skeleton
  folder under `apps/<name>/` (an `app.yml` manifest + a `compose.yml`) and is run
  by the manager as its **own separate `docker compose` project**.
- Because each app is its own project, it gets its own network, its own volumes,
  and its own database. Two apps that both use Postgres never share one.
- Only an app's **web/target port** is published, to `127.0.0.1`. Databases and
  internal tiers are never bound to the host. Every app's web service also joins a
  shared `vuln-net` network, so a scanner running in a container can reach them by
  name (e.g. `http://dvwa`) with no host port at all.

## Quick start

```sh
cd vuln_apps
./vam start --all      # ONE command: builds the manager, starts every light app,
                       # and runs each app's first-time setup automatically
./vam status           # what's running + URLs
./vam stop --all       # stop everything
```

That single `./vam start --all` also runs the one-time setup each app needs
(DVWA's create-database, bWAPP's install, VAmPI's seed), so every app is usable
the moment it reports `running` - no manual `/setup.php` or `/install.php` clicks.

Want the manager to stay up as a live status monitor? Run `docker compose up -d`
first, then use `./vam ...` as above.

`./vam <cmd>` is just a wrapper. The exact same thing without it:

```sh
docker compose run --rm vuln_apps_manager start --all
docker compose run --rm vuln_apps_manager status
```

## Manager commands

| Command | What it does |
|---|---|
| `./vam list` | list all apps, their state and URL |
| `./vam start <app...> \| --all [--heavy]` | start app(s). `--all` skips heavy apps unless `--heavy` |
| `./vam stop <app...> \| --all` | stop app(s) |
| `./vam restart <app...> \| --all` | restart app(s) |
| `./vam status` | fleet status table |
| `./vam logs <app> [-f]` | tail an app's logs |
| `./vam pull <app...> \| --all` | pre-pull images |
| `./vam ports` | host-port map + clash check |
| `./vam doctor` | environment + port sanity checks |

Examples: `./vam start juice-shop dvwa`, `./vam start crapi --heavy`, `./vam logs webgoat -f`.

## Apps and ports

All URLs are `http://127.0.0.1:<port>` (loopback only).

| App | Port | Stack | Notes |
|---|---|---|---|
| juice-shop | 7001 | Node / Angular | modern SPA + REST |
| dvwa | 7002 | PHP / MariaDB | DB auto-created on start; login admin/password |
| webgoat | 7003 | Java | + WebWolf on 7004 (OOB catcher) |
| vampi | 7005 | Python / Flask | OWASP API Top 10 |
| dvga | 7006 | Python / GraphQL | `/graphql` |
| bwapp | 7007 | PHP | auto-installed on start; login bee/bug |
| log4shell | 7009 | Java / Spring | blind-RCE -> OAST |
| crapi | 7010 | Node/Java/Python | **heavy**; mailhog on 7011 |
| faultline | 8088 | SvelteKit/Rust/PG/Redis | fetched from GitHub (see below) |

Reserved host-port block: **`7001-7099`**. `./vam ports` shows the live map and
flags any clash.

## Adding a new app

Drop a folder under `apps/`:

```
apps/<name>/
  app.yml       # name, description, category, stack, url
  compose.yml   # the container(s): image, ports (127.0.0.1 only), any DB
  setup.sh      # optional: one-time init run after start (see below)
```

Rules that keep the fleet clean:

- Bind only the web/target port, to `127.0.0.1:<free 70xx port>`.
- **Single-container apps:** put the service on `[vuln-net]` only. Do NOT add a
  per-project network - that conserves Docker's address pool (too many networks
  and Docker fails with "all predefined address pools have been fully subnetted").
- **Apps with a database:** put the app on `[default, vuln-net]` and the DB on
  `[default]` only (private, no host binding). Give each app its own DB service
  and volume (do not share). Declare `vuln-net` as `external: true`.
- **First-run setup:** if the app needs a one-time init (create DB, install,
  seed), add an `apps/<name>/setup.sh`. The manager runs it after `start`, from
  inside the manager container (which is on `vuln-net` and has `curl`), so it can
  reach the app by service name, e.g. `curl http://<service>/install.php`.

That is it. The manager picks it up automatically (`./vam list`).

For an app whose source lives in a **git repo** (like faultline), skip
`compose.yml` and instead put `repo:` (the clone URL) and `compose:` (the compose
path inside that repo) in `app.yml`. The manager clones it into
`apps/<name>/src/` (gitignored) on first start, so no source is vendored here.

## Vulnerability catalogs

`vulns/` holds a per-app "answer key" (what each target is supposed to be
vulnerable to), so you can check a scanner's findings against ground truth. See
[`vulns/README.md`](vulns/README.md). Detailed local catalogs exist for
[faultline](vulns/faultline.md) and [crapi](vulns/crapi.md); the upstream apps
point at their own authoritative answer keys.

## crAPI (heavy)

crAPI runs Postgres + Mongo + three app tiers (~2 GB), so `--all` skips it. Start
it explicitly: `./vam start crapi --heavy`. First boot is slow; sign-up OTP and
reset mails land in mailhog at http://127.0.0.1:7011.

## faultline (fetched from GitHub)

faultline is Clickswave's own full-stack target. Its source is **not** vendored
here; the manager clones it from github.com/clickswave/faultline on first start:

```sh
./vam start faultline    # clones the repo into apps/faultline/src/, then builds + runs it
```

The first start builds it (Rust; slow). Update the checkout later with
`./vam pull faultline`. Then open http://127.0.0.1:8088. Demo logins:
`alice@example.com` / `password`, `admin@faultline.local` / `admin`.

## Notes

- `docker compose down` stops only the **manager**. Stop the apps first with
  `./vam stop --all` (they are separate projects).
- The manager talks to the host Docker daemon via the mounted socket; that is why
  it can start and watch the other containers.
