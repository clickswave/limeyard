#!/usr/bin/env python3
"""lime - the limeyard control plane.

limeyard is a security testing lab. It drives a fleet of deliberately
vulnerable targets, each defined by a skeleton under targets/<kind>/<slug>/
(a target.yml manifest + a compose.yml) and run as its OWN isolated
`docker compose` project, so every target gets its own network, volumes and
database. Two targets that both use Postgres never share one.

Kinds:
  web api bench cve service estate edge control mobile

Beyond single targets there are scenarios (scenarios/<slug>/), which wire
several targets into a network topology with authoritative DNS, so asset
discovery engines have something real to enumerate.

Dev/testing tool. It talks to the host Docker daemon via the mounted socket.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("LIMEYARD_DIR") or os.path.dirname(os.path.dirname(HERE))
TARGETS_DIR = os.path.join(BASE, "targets")
SCENARIOS_DIR = os.path.join(BASE, "scenarios")
TRUTH_DIR = os.path.join(BASE, "truth")

WEB_NET = os.environ.get("LIME_WEB_NET", "lime-web")
LAB_NET = os.environ.get("LIME_LAB_NET", "lime-lab")
LAB_SUBNET = os.environ.get("LIME_LAB_SUBNET", "10.66.0.0/16")
PREFIX = "lime-"

KINDS = ["web", "api", "bench", "cve", "service", "estate", "edge", "control", "mobile"]

_TTY = sys.stdout.isatty()
_COL = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m",
        "b": "\033[1;34m", "d": "\033[2m", "x": "\033[0m"}


def col(s, c):
    return f"{_COL[c]}{s}{_COL['x']}" if _TTY and c in _COL else s


def die(msg):
    print(col("error: " + msg, "r"), file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------ loading ---
def _read_manifest(d):
    """target.yml, falling back to the pre-limeyard app.yml name."""
    for fn in ("target.yml", "app.yml"):
        p = os.path.join(d, fn)
        if os.path.exists(p) and yaml:
            try:
                with open(p) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(col(f"warning: {p} parse error: {e}", "y"), file=sys.stderr)
                return {}
    return {}


def load_targets():
    """Discover targets from targets/<kind>/<slug>/. Returns {slug: meta}."""
    out = {}
    if not os.path.isdir(TARGETS_DIR):
        return out
    for kind in sorted(os.listdir(TARGETS_DIR)):
        kd = os.path.join(TARGETS_DIR, kind)
        if not os.path.isdir(kd):
            continue
        for slug in sorted(os.listdir(kd)):
            d = os.path.join(kd, slug)
            if not os.path.isdir(d):
                continue
            meta = _read_manifest(d)
            meta.setdefault("name", slug)
            meta.setdefault("kind", kind)
            meta["slug"] = slug
            meta["dir"] = d
            comp = meta.get("compose")
            if meta.get("repo"):
                # Repo-backed: source is fetched at runtime into <target>/src and
                # never vendored here.
                meta["src_dir"] = os.path.join(d, "src")
                if comp:
                    # `compose` names a path WITHIN the fetched repo, so we run
                    # theirs as-is. faultline does this.
                    meta["compose_path"] = os.path.join(meta["src_dir"], comp)
                elif os.path.exists(os.path.join(d, "compose.yml")):
                    # We ship our own compose that builds from ./src: upstream
                    # provides the source, we keep control of the hardening, and
                    # `lime audit` can still see the file.
                    meta["compose_path"] = os.path.join(d, "compose.yml")
                else:
                    meta["compose_path"] = os.path.join(meta["src_dir"], "docker-compose.yml")
            elif comp:
                meta["compose_path"] = comp if os.path.isabs(comp) else os.path.normpath(os.path.join(d, comp))
            else:
                meta["compose_path"] = os.path.join(d, "compose.yml")
            meta["project"] = meta.get("project", PREFIX + slug)
            meta["truth_path"] = os.path.join(d, meta.get("truth", "truth.yml"))
            if slug in out:
                print(col(f"warning: duplicate target slug '{slug}'", "y"), file=sys.stderr)
            out[slug] = meta
    return out


def load_scenarios():
    out = {}
    if not os.path.isdir(SCENARIOS_DIR):
        return out
    for slug in sorted(os.listdir(SCENARIOS_DIR)):
        d = os.path.join(SCENARIOS_DIR, slug)
        if not os.path.isdir(d):
            continue
        meta = {}
        p = os.path.join(d, "scenario.yml")
        if os.path.exists(p) and yaml:
            try:
                with open(p) as f:
                    meta = yaml.safe_load(f) or {}
            except Exception as e:
                print(col(f"warning: {p} parse error: {e}", "y"), file=sys.stderr)
        meta.setdefault("name", slug)
        meta["slug"] = slug
        meta["dir"] = d
        meta["compose_path"] = os.path.join(d, "compose.yml")
        meta["project"] = PREFIX + "scn-" + slug
        meta["truth_path"] = os.path.join(d, "truth.yml")
        out[slug] = meta
    return out


def load_truth(t):
    p = t.get("truth_path")
    if not (p and os.path.exists(p) and yaml):
        return None
    try:
        with open(p) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(col(f"warning: {p} parse error: {e}", "y"), file=sys.stderr)
        return None


# ------------------------------------------------------------------ docker ---
def dc(t, *args, capture=False):
    """Run `docker compose` for one target's project."""
    cmd = ["docker", "compose", "-p", t["project"], "-f", t["compose_path"], *args]
    cwd = os.path.dirname(t["compose_path"]) or None
    if capture:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=cwd)


COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT_NAME", "limeyard")


def ensure_network(name=WEB_NET, subnet=None):
    """Create a lab network if it is absent. The top-level compose file declares
    the same networks, so they are created with the labels compose stamps on
    its own, and whichever side gets there first, the other recognises it
    instead of warning that the network was not created by compose."""
    r = subprocess.run(["docker", "network", "inspect", name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        cmd = ["docker", "network", "create",
               "--label", f"com.docker.compose.project={COMPOSE_PROJECT}",
               "--label", f"com.docker.compose.network={name}",
               "--label", "com.docker.compose.version=2"]
        if subnet:
            cmd += ["--subnet", subnet]
        cmd.append(name)
        subprocess.run(cmd, stdout=subprocess.DEVNULL)


def ensure_networks():
    ensure_network(WEB_NET)
    ensure_network(LAB_NET, LAB_SUBNET)


def containers(t):
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter",
         f"label=com.docker.compose.project={t['project']}",
         "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"],
        capture_output=True, text=True)
    rows = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append(tuple(parts))
    return rows


def state_of(t):
    cs = containers(t)
    if not cs:
        return "stopped", "d"
    running = sum(1 for _, s, _ in cs if s == "running")
    if any("unhealthy" in st for _, _, st in cs):
        return "unhealthy", "r"
    if any("health: starting" in st or "Restarting" in st for _, _, st in cs):
        return "starting", "y"
    if running == len(cs):
        return "running", "g"
    return f"partial {running}/{len(cs)}", "y"


def fetched(t):
    return not t.get("repo") or os.path.isdir(os.path.join(t.get("src_dir", ""), ".git"))


def is_fixture(t):
    """A target with no service to run. Mobile APKs are artifacts: you install
    them and drive them with Tracer, there is nothing to `docker compose up`."""
    return bool(t.get("artifact")) or t.get("kind") == "mobile"


def missing(t):
    if is_fixture(t):
        return False
    return not os.path.exists(t["compose_path"])


def ensure_src(t):
    """Clone a repo-backed target's source on first use."""
    if fetched(t):
        return True
    repo, src = t["repo"], t["src_dir"]
    print(col(f"  fetching {t['slug']} from {repo}", "d"))
    cmd = ["git", "clone", "--depth", "1"]
    if t.get("ref"):
        cmd += ["--branch", str(t["ref"])]
    cmd += [repo, src]
    return subprocess.run(cmd).returncode == 0


def run_setup(t):
    hook = os.path.join(t["dir"], "setup.sh")
    if os.path.exists(hook):
        print(col(f"  setting up {t['slug']} (one-time, may wait for readiness)...", "d"))
        subprocess.run(["sh", hook])


# ----------------------------------------------------------------- setup ---
# Every manifest carries a measured `resources` block. The wizard and the panel
# sum those to say what a selection will cost before anything starts.

def resources_of(t):
    r = t.get("resources") or {}
    if not r and not is_fixture(t):
        # Unmeasured: assume a modest single container so the estimate errs high.
        r = {"containers": 1, "ram_mb": 256, "disk_gb": 0.5, "cpu_idle_pct": 0.5, "guess": True}
    return {"containers": int(r.get("containers", 0)), "ram_mb": int(r.get("ram_mb", 0)),
            "disk_gb": float(r.get("disk_gb", 0)), "cpu_idle_pct": float(r.get("cpu_idle_pct", 0)),
            "guess": bool(r.get("guess", False))}


def estimate(items):
    tot = {"containers": 0, "ram_mb": 0, "disk_gb": 0.0, "cpu_idle_pct": 0.0, "guessed": 0}
    for t in items:
        r = resources_of(t)
        tot["containers"] += r["containers"]
        tot["ram_mb"] += r["ram_mb"]
        tot["disk_gb"] += r["disk_gb"]
        tot["cpu_idle_pct"] += r["cpu_idle_pct"]
        tot["guessed"] += 1 if r["guess"] else 0
    tot["disk_gb"] = round(tot["disk_gb"], 1)
    tot["cpu_idle_pct"] = round(tot["cpu_idle_pct"], 1)
    return tot


def host_headroom():
    """What the box has to give: available RAM, free disk, cpus."""
    ram_gb = None
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                mem[k] = int(v.split()[0])
        ram_gb = mem["MemAvailable"] / 1048576
    except Exception:
        pass
    pct, disk_gb = _disk_free_pct()
    return {"ram_avail_gb": ram_gb, "disk_free_gb": disk_gb, "cpus": os.cpu_count()}


def _ask(prompt, default=""):
    try:
        a = input(prompt).strip()
    except EOFError:
        print()
        return default
    return a or default


def cmd_measure(targets, args):
    """Print the `resources` block for running targets. Contributors paste the
    output into target.yml; the installer and the panel add these up to say
    what a selection costs before it is started, so a guess here is a lie
    there. Measure one target at a time, settled, for a number worth having."""
    items = {**targets, **load_scenarios()}
    names = args.names or [k for k, v in items.items()
                           if not is_fixture(v) and state_of(v)[0] == "running"]
    ps = subprocess.run(["docker", "ps", "--format",
                         '{{.Names}}\t{{.Label "com.docker.compose.project"}}'],
                        capture_output=True, text=True).stdout
    owner = {}
    for line in ps.strip().splitlines():
        parts = line.split("\t")
        owner[parts[0]] = parts[1] if len(parts) > 1 else ""
    st = subprocess.run(["docker", "stats", "--no-stream", "--format",
                         "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"],
                        capture_output=True, text=True).stdout

    def as_mb(chunk):
        used = chunk.split("/")[0].strip()
        for unit, factor in (("GiB", 1024), ("MiB", 1), ("KiB", 1 / 1024), ("B", 1 / 1048576)):
            if used.endswith(unit):
                try:
                    return float(used[: -len(unit)]) * factor
                except ValueError:
                    return 0.0
        return 0.0

    mem, cpu, count = {}, {}, {}
    for line in st.strip().splitlines():
        name, m, c = line.split("\t")
        proj = owner.get(name, "")
        mem[proj] = mem.get(proj, 0.0) + as_mb(m)
        cpu[proj] = cpu.get(proj, 0.0) + float(c.rstrip("%") or 0)
        count[proj] = count.get(proj, 0) + 1

    rc = 0
    for slug in names:
        t = items.get(slug)
        if t is None:
            print(col(f"unknown target or scenario '{slug}'", "r"), file=sys.stderr)
            rc = 1
            continue
        if is_fixture(t):
            print(f"# {slug}: fixture, nothing to run")
            print("resources:\n  containers: 0\n  ram_mb: 0\n  disk_gb: 0\n  cpu_idle_pct: 0\n")
            continue
        proj = t["project"]
        if not count.get(proj):
            print(col(f"# {slug}: not running. Start it, let it settle, measure again.", "y"))
            rc = 1
            continue
        disk, unknown = 0, []
        for svc in compose_services(t):
            ref = svc["image"] or f"{proj}-{svc['service']}"
            r = subprocess.run(["docker", "image", "inspect", ref, "--format", "{{.Size}}"],
                               capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip().isdigit():
                disk += int(r.stdout.strip())
            else:
                unknown.append(ref)
        print(f"# {slug}, measured idle on this box, {time.strftime('%Y-%m-%d')}")
        if unknown:
            print(col(f"# image not present, disk is short by it: {', '.join(unknown)}", "y"))
        print("resources:")
        print(f"  containers: {count[proj]}")
        print(f"  ram_mb: {round(mem[proj])}")
        print(f"  disk_gb: {round(disk / 1e9, 1)}")
        print(f"  cpu_idle_pct: {round(cpu[proj], 1)}\n")
    return rc


def cmd_setup(targets, args):
    """Interactive first run: show the fleet and what it costs, take a
    selection, compare it with the host, confirm, start."""
    scenarios = load_scenarios()
    runnable = [t for t in targets.values() if not is_fixture(t)]
    light = [t for t in runnable if not is_heavy(t)]
    heavy = [t for t in runnable if is_heavy(t)]

    print()
    print(col("What is in the lab", "b"))
    print(f"  {'target':14} {'kind':8} {'weight':6} {'ctrs':>4} {'ram':>7} {'disk':>7}  description")
    for t in sorted(runnable, key=lambda x: (is_heavy(x), x.get("kind", ""), x["slug"])):
        r = resources_of(t)
        print(f"  {t['slug']:14} {t.get('kind', ''):8} {'heavy' if is_heavy(t) else 'light':6} "
              f"{r['containers']:>4} {r['ram_mb']:>4} MB {r['disk_gb']:>4.1f} GB  "
              f"{(t.get('description') or '')[:60]}")
    for s in scenarios.values():
        r = resources_of(s)
        print(f"  {s['slug']:14} {'scenario':8} {'':6} {r['containers']:>4} {r['ram_mb']:>4} MB "
              f"{r['disk_gb']:>4.1f} GB  {(s.get('description') or '').split('.')[0][:60]}")
    fixtures = [t for t in targets.values() if is_fixture(t)]
    if fixtures:
        print(f"  {', '.join(t['slug'] for t in fixtures)}: fixture, nothing to run")
    print()

    mode = None
    if getattr(args, "all", False):
        mode = "all"
    elif getattr(args, "light", False):
        mode = "light"
    elif getattr(args, "none", False):
        mode = "none"
    elif getattr(args, "pick", None):
        mode = "pick"
    if mode is None:
        print("What should run?")
        print(f"  1  every light target and the estate scenario   ({len(light)} targets, recommended)")
        print(f"  2  everything, heavy ones too                    ({len(runnable)} targets)")
        print("  3  let me pick")
        print("  4  nothing yet, just the panel")
        mode = {"1": "light", "2": "all", "3": "pick", "4": "none", "": "light"}.get(_ask("  > [1] "), None)
        while mode is None:
            mode = {"1": "light", "2": "all", "3": "pick", "4": "none"}.get(_ask("  1, 2, 3 or 4: "), None)

    chosen_t, chosen_s = [], []
    if mode == "light":
        chosen_t, chosen_s = light, list(scenarios.values())
    elif mode == "all":
        chosen_t, chosen_s = runnable, list(scenarios.values())
    elif mode == "pick":
        raw = getattr(args, "pick", None)
        if not raw:
            print("  Type slugs, kinds or scenario names, comma separated. `light` and `all` work too.")
            raw = _ask("  > ")
        want = [w.strip().lower() for w in str(raw).split(",") if w.strip()]
        for w in want:
            if w == "light":
                chosen_t += light
            elif w == "all":
                chosen_t += runnable
            elif w in targets and not is_fixture(targets[w]):
                chosen_t.append(targets[w])
            elif w in scenarios:
                chosen_s.append(scenarios[w])
            elif w in KINDS:
                chosen_t += [t for t in runnable if t.get("kind") == w]
            else:
                print(col(f"  unknown: {w}", "y"))
        chosen_t = list({t["slug"]: t for t in chosen_t}.values())
        chosen_s = list({s["slug"]: s for s in chosen_s}.values())

    if not chosen_t and not chosen_s:
        print()
        print("Nothing started. The panel is at http://127.0.0.1:7000; start targets from there,")
        print("or `./lime start --all`, or run `./lime setup` again.")
        return 0

    est = estimate(chosen_t + chosen_s)
    head = host_headroom()
    print()
    print("This selection, idle, on the box it was measured on:")
    print(f"  {len(chosen_t)} targets, {len(chosen_s)} scenarios, {est['containers']} containers")
    print(f"  RAM  about {est['ram_mb'] / 1024:.1f} GB resident"
          + (f"  (host has {head['ram_avail_gb']:.1f} GB available)" if head["ram_avail_gb"] else ""))
    print(f"  disk about {est['disk_gb']:.1f} GB of images to pull"
          + (f"  (host has {head['disk_free_gb']:.0f} GB free for them)"
             if head["disk_free_gb"] else ""))
    print(f"  CPU  near idle once up ({est['cpu_idle_pct']:.0f}% of one core); "
          f"pulling and first boots are the busy part")
    if est["guessed"]:
        print(col(f"  {est['guessed']} of these have no measurement and are guessed high.", "y"))
    problems = []
    if head["ram_avail_gb"] and est["ram_mb"] / 1024 > head["ram_avail_gb"] * 0.7:
        problems.append("RAM: this would take most of what is free; expect swapping.")
    if head["disk_free_gb"] and est["disk_gb"] * 1.3 > head["disk_free_gb"]:
        problems.append("disk: the images plus their layers may not fit.")
    hv = [t["slug"] for t in chosen_t if is_heavy(t)]
    if hv:
        problems.append(f"heavy: {', '.join(hv)} build from source or pull gigabytes; minutes, not seconds.")
    for p in problems:
        print(col(f"  warning, {p}", "y"))
    print()
    if not getattr(args, "yes", False):
        if _ask("Start it? [y/N] ").lower() not in ("y", "yes"):
            print("Nothing started.")
            return 0

    ensure_networks()
    ok = True
    for t in chosen_t:
        print(col(f"\n== {t['slug']}", "b"))
        if t.get("repo") and not ensure_src(t):
            ok = False
            continue
        if missing(t):
            print(col(f"  compose missing: {t['compose_path']}", "r"))
            ok = False
            continue
        if dc(t, "up", "-d").returncode != 0:
            ok = False
            continue
        run_setup(t)
    for s in chosen_s:
        print(f"\n== scenario {s['slug']}")
        if dc(s, "up", "-d").returncode != 0:
            ok = False
            continue
        run_setup(s)
    print()
    print(col("Up." if ok else "Up, with failures above.", "g" if ok else "y"))
    print("  panel   http://127.0.0.1:7000")
    print("  status  ./lime status")
    print("  stop    ./lime stop --all --heavy")
    return 0 if ok else 1


def resolve(targets, names, all_flag, heavy, kind=None):
    pool = targets.values()
    if kind:
        pool = [t for t in pool if t.get("kind") == kind]
        if not pool:
            die(f"no targets of kind '{kind}'  (kinds: {', '.join(KINDS)})")
    if all_flag or (kind and not names):
        return [t for t in pool if not (t.get("heavy") or t.get("weight") == "heavy") or heavy]
    if not names:
        die("name one or more targets, or pass --all or --kind  (see: lime list)")
    out = []
    for n in names:
        if n not in targets:
            die(f"unknown target '{n}'  (see: lime list)")
        out.append(targets[n])
    return out


def is_heavy(t):
    return bool(t.get("heavy") or t.get("weight") == "heavy")


def _pad(s, w):
    return s + " " * max(0, w - len(s))


def _author(t):
    up = t.get("upstream") or {}
    a = up.get("author")
    if not a:
        return "-"
    if up.get("packager") and up["packager"] != a:
        return f"{a} (pkg: {up['packager']})"
    return a


# ---------------------------------------------------------------- commands ---
def cmd_list(targets, args):
    kind_filter = getattr(args, "kind", None)
    print(f"{_pad('TARGET', 13)}  {_pad('KIND', 8)}  {_pad('STATE', 10)}  "
          f"{_pad('URL', 30)}  {_pad('AUTHOR', 28)}  LICENSE")
    heavy_stopped = []
    for t in targets.values():
        if kind_filter and t.get("kind") != kind_filter:
            continue
        label, c = state_of(t)
        if is_heavy(t) and label == "stopped":
            heavy_stopped.append(t["slug"])
        up = t.get("upstream") or {}
        lic = up.get("license", "?")
        lic_col = "r" if lic in ("none declared", "?") else "d"
        print(f"{_pad(t['slug'], 13)}  {_pad(t.get('kind', '?'), 8)}  {col(_pad(label, 10), c)}  "
              f"{_pad(t.get('url', '-'), 30)}  {_pad(_author(t)[:28], 28)}  {col(lic, lic_col)}")
    if heavy_stopped:
        print(col(f"note: {', '.join(heavy_stopped)} are heavy and not started by --all; "
                  f"run: ./lime start {heavy_stopped[0]} --heavy", "d"))


cmd_status = cmd_list


def _credits_markdown(targets):
    """The README's Credits section, generated. CI regenerates it so the repo
    front page can never drift from the manifests."""
    out = ["<!-- generated by `lime credits --markdown`; do not edit by hand -->",
           "", "limeyard runs other people's work. Every target below was built by",
           "someone else unless it says Clickswave.", ""]
    by_kind = {}
    for t in targets.values():
        by_kind.setdefault(t.get("kind", "?"), []).append(t)
    for kind in sorted(by_kind):
        out += [f"### {kind}", "", "| target | author | licence | source |", "|---|---|---|---|"]
        for t in sorted(by_kind[kind], key=lambda x: x["slug"]):
            up = t.get("upstream") or {}
            a = _author(t)
            lic = up.get("license", "unknown")
            repo = f"[repo]({up['repo']})" if up.get("repo") else "-"
            out.append(f"| {t['name']} | {a} | {lic} | {repo} |")
        out.append("")
    return "\n".join(out)


def cmd_credits(targets, args):
    """Attribution. Every target we did not write credits whoever built it."""
    if getattr(args, "markdown", False):
        print(_credits_markdown(targets))
        return
    print("limeyard runs other people's work. Credit where it is due.\n")
    by_kind = {}
    for t in targets.values():
        by_kind.setdefault(t.get("kind", "?"), []).append(t)
    for kind in sorted(by_kind):
        print(col(f"## {kind}", "b"))
        for t in sorted(by_kind[kind], key=lambda x: x["slug"]):
            up = t.get("upstream") or {}
            print(f"  {col(t['name'], 'b')}  ({t['slug']})")
            print(f"    author   {up.get('author', col('MISSING', 'r'))}")
            if up.get("packager"):
                print(f"    packaged {up['packager']}")
            if up.get("repo"):
                print(f"    repo     {up['repo']}")
            if up.get("homepage"):
                print(f"    home     {up['homepage']}")
            lic = up.get("license", "unknown")
            print(f"    license  {col(lic, 'r') if lic in ('none declared', 'unknown') else lic}")
            if up.get("note"):
                print(col(f"    note     {up['note'].strip()}", "d"))
        print()


def cmd_start(targets, args):
    ensure_networks()
    for t in resolve(targets, args.names, args.all, args.heavy, getattr(args, "kind", None)):
        if is_fixture(t):
            a = t.get("artifact") or {}
            print(col(f"==> {t['slug']} is a fixture, nothing to start", "d"))
            if a.get("release"):
                print(col(f"    artifact: {a.get('file') or a['type']} from {a['release']}", "d"))
            continue
        if t.get("repo") and not ensure_src(t):
            print(col(f"  FAILED to fetch {t['slug']} source", "r"))
            continue
        if missing(t):
            print(col(f"  skip {t['slug']}: compose not found ({t['compose_path']})", "y"))
            continue
        print(col(f"==> starting {t['slug']}  ({t['name']})", "b"))
        if dc(t, "up", "-d").returncode != 0:
            print(col(f"  FAILED: {t['slug']}", "r"))
            continue
        run_setup(t)
    if args.all:
        skipped = [t["slug"] for t in targets.values() if is_heavy(t) and not args.heavy]
        if skipped:
            print(col(f"note: skipped heavy targets ({', '.join(skipped)}); add --heavy to include", "d"))
    print()
    cmd_list(targets, args)


def cmd_stop(targets, args):
    for t in resolve(targets, args.names, args.all, True, getattr(args, "kind", None)):
        if missing(t):
            continue
        print(col(f"==> stopping {t['slug']}", "b"))
        dc(t, "down")


def cmd_restart(targets, args):
    cmd_stop(targets, args)
    cmd_start(targets, args)


def cmd_pull(targets, args):
    for t in resolve(targets, args.names, args.all, args.heavy, getattr(args, "kind", None)):
        if t.get("repo"):
            if fetched(t):
                print(col(f"==> updating {t['slug']} source", "b"))
                subprocess.run(["git", "-C", t["src_dir"], "pull", "--ff-only"])
            else:
                ensure_src(t)
        if missing(t):
            continue
        print(col(f"==> pulling {t['slug']} images", "b"))
        dc(t, "pull")


def cmd_logs(targets, args):
    if args.name not in targets:
        die(f"unknown target '{args.name}'")
    dc(targets[args.name], "logs", *(["-f"] if args.follow else ["--tail", "200"]))


def compose_doc(t):
    """The parsed compose file, or {} when absent or unparseable."""
    if not (yaml and os.path.exists(t["compose_path"])):
        return {}
    try:
        with open(t["compose_path"]) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def compose_services(t):
    """[{service, container_name, image, pinned, lab_ip}] for every service."""
    out = []
    for sname, svc in (compose_doc(t).get("services") or {}).items():
        img = str(svc.get("image") or "")
        ip = None
        for _, net in ((svc.get("networks") or {}).items()
                       if isinstance(svc.get("networks"), dict) else []):
            if isinstance(net, dict) and net.get("ipv4_address"):
                ip = str(net["ipv4_address"])
        out.append({"service": sname,
                    "container_name": svc.get("container_name"),
                    "image": img or None,
                    "pinned": ("@sha256:" in img) if img else None,
                    "lab_ip": ip})
    return out


def host_states(s):
    """Per-host state for a scenario: {lab_ip: state}. A scenario is several
    containers with static addresses, and the panel wants to say which of
    them is actually up, not just whether the compose project exists."""
    by_name = {name: st for name, st, _ in containers(s)}
    out = {}
    for svc in compose_services(s):
        if not svc["lab_ip"]:
            continue
        name = svc["container_name"] or f"{s['project']}-{svc['service']}-1"
        st = by_name.get(name)
        out[svc["lab_ip"]] = st if st else "stopped"
    return out


def host_ports(t):
    if not (yaml and os.path.exists(t["compose_path"])):
        return []
    try:
        with open(t["compose_path"]) as f:
            doc = yaml.safe_load(f) or {}
    except Exception:
        return []
    out = []
    for sname, svc in (doc.get("services") or {}).items():
        for p in (svc.get("ports") or []):
            if isinstance(p, dict):
                if p.get("published"):
                    out.append((str(p["published"]), sname, str(p.get("host_ip", ""))))
            else:
                parts = str(p).split(":")
                if len(parts) == 3:
                    out.append((parts[1], sname, parts[0]))
                elif len(parts) == 2:
                    out.append((parts[0], sname, ""))
    return out


def cmd_ports(targets, args):
    seen, exposed = {}, []
    for t in targets.values():
        for hp, svc, ip in host_ports(t):
            seen.setdefault(hp, []).append(f"{t['slug']}/{svc}")
            if ip and ip not in ("127.0.0.1", "localhost"):
                exposed.append(f"{t['slug']}/{svc} on {ip}:{hp}")
    clash = False
    for hp in sorted(seen, key=lambda x: int(x) if x.isdigit() else 0):
        owners = seen[hp]
        if len(owners) > 1:
            clash = True
        line = f"  127.0.0.1:{_pad(hp, 6)} -> {', '.join(owners)}"
        print(col(line + "   CLASH", "r") if len(owners) > 1 else line)
    print(col("PORT CLASH DETECTED", "r") if clash else col("no host-port clashes", "g"))
    if exposed:
        print(col("DANGER: targets bound off-loopback:", "r"))
        for e in exposed:
            print(col(f"  {e}", "r"))
    return clash


def disk_level(pct, gb):
    """ok | low | crit | unknown. Percent alone lies on a big disk: 12% of a
    terabyte is plenty, so both the share and the absolute space must be
    short before anything is refused."""
    if pct is None or gb is None:
        return "unknown"
    if pct < 5 and gb < 20:
        return "crit"
    if pct < 12 and gb < 40:
        return "low"
    return "ok"


_cpu_last = None


def _cpu_times():
    with open("/proc/stat") as f:
        vals = [int(x) for x in f.readline().split()[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    return sum(vals), idle


def host_load():
    """CPU, RAM and load for the machine the lab runs on. /proc is not
    namespaced for these files, so a container reads the host's numbers.
    CPU is the busy share since the previous call, which is what a ticking
    stream wants; the first call samples twice."""
    global _cpu_last
    cpu = None
    try:
        total, idle = _cpu_times()
        if _cpu_last is None:
            _cpu_last = (total, idle)
            time.sleep(0.25)
            total, idle = _cpu_times()
        dt, di = total - _cpu_last[0], idle - _cpu_last[1]
        if dt > 0:
            _cpu_last = (total, idle)
            cpu = round(100.0 * (dt - di) / dt, 1)
    except Exception:
        pass
    ram = None
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                mem[k] = int(v.split()[0])
        total_gb = mem["MemTotal"] / 1048576
        avail_gb = mem["MemAvailable"] / 1048576
        ram = {"total_gb": round(total_gb, 1), "used_gb": round(total_gb - avail_gb, 1),
               "pct": round(100.0 * (1 - avail_gb / total_gb), 1)}
    except Exception:
        pass
    load1 = None
    try:
        with open("/proc/loadavg") as f:
            load1 = float(f.read().split()[0])
    except Exception:
        pass
    return {"cpu_pct": cpu, "ram": ram, "load1": load1, "cpus": os.cpu_count()}


def disk_view():
    pct, gb = _disk_free_pct()
    return {"free_pct": round(pct, 1) if pct else None,
            "free_gb": round(gb, 1) if gb else None,
            "level": disk_level(pct, gb),
            "heavy_blocked": disk_level(pct, gb) == "crit"}


def _fs_free(path):
    try:
        st = os.statvfs(path)
        if not st.f_blocks:
            return None
        return {"path": path, "pct": 100.0 * st.f_bavail / st.f_blocks,
                "gb": st.f_bavail * st.f_frsize / 1e9}
    except Exception:
        return None


_docker_root = None


def docker_root():
    """Where Docker keeps images and volumes. Inside the control container the
    host's /var/lib/docker is not mounted, but the container's own writable
    layer lives on that same filesystem, so "/" measures it correctly."""
    global _docker_root
    if _docker_root is None:
        r = subprocess.run(["docker", "info", "--format", "{{.DockerRootDir}}"],
                           capture_output=True, text=True)
        root = r.stdout.strip() if r.returncode == 0 else ""
        _docker_root = root if root and os.path.isdir(root) else "/"
    return _docker_root


def _disk_free_pct():
    """Free space where it actually runs out. Images and volumes go under
    Docker's data root; fetched sources go in the checkout. Those are often
    different disks, and a checkout on a small partition said "21 GB free"
    while Docker had 104, so take whichever is tighter."""
    seen = [f for f in (_fs_free(docker_root()), _fs_free(BASE)) if f]
    if not seen:
        return None, None
    f = min(seen, key=lambda x: x["gb"])
    return f["pct"], f["gb"]


def cmd_doctor(targets, args):
    if getattr(args, "fix", False):
        from api import fix
        res = fix()
        for r in res["results"]:
            print((col("[ok] ", "g") if r["ok"] else col("[!!] ", "r")) + f"{r['id']}: {r['message']}")
        print()
    ok = True
    dok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    print(("[ok] " if dok else "[!!] ") + "docker daemon reachable")
    ok &= dok
    for n in (WEB_NET, LAB_NET):
        nok = subprocess.run(["docker", "network", "inspect", n],
                             capture_output=True).returncode == 0
        print(f"[{'ok' if nok else '..'}] network '{n}' "
              + ("present" if nok else "absent (created on first start)"))

    # Attribution is a hard gate: a target may not exist without crediting its author.
    for t in targets.values():
        up = t.get("upstream") or {}
        if not up.get("author"):
            print(col(f"[!!] {t['slug']}: target.yml has no upstream.author "
                      f"(attribution is required, see truth/schema.md)", "r"))
            ok = False
        elif not up.get("license"):
            print(col(f"[!!] {t['slug']}: upstream.license missing "
                      f"(use the SPDX id, or the literal 'none declared')", "y"))

    # Staleness: a target verified long ago is a build waiting to fail.
    today = time.strftime("%Y-%m-%d")
    for t in targets.values():
        v = ((t.get("upstream") or {}).get("verified") or "")
        v = str(v)[:10]
        if v and v < time.strftime("%Y-%m-%d", time.localtime(time.time() - 180 * 86400)):
            print(col(f"[..] {t['slug']}: last verified {v}, over 180 days ago", "y"))

    for t in targets.values():
        if is_fixture(t):
            print(f"[ok] {t['slug']}: fixture ({(t.get('artifact') or {}).get('type', 'artifact')}), nothing to run")
            continue
        if missing(t):
            if t.get("repo"):
                print(f"[..] {t['slug']}: source not fetched yet (git clone on start)")
            else:
                print(col(f"[!!] {t['slug']}: compose missing ({t['compose_path']})", "r"))
                ok = False
        if not os.path.exists(t["truth_path"]):
            print(col(f"[..] {t['slug']}: no truth.yml, it cannot be scored", "y"))

    pct, gb = _disk_free_pct()
    if pct is not None:
        lvl = disk_level(pct, gb)
        c = {"crit": "r", "low": "y"}.get(lvl, "g")
        print(col(f"[{'!!' if lvl == 'crit' else 'ok'}] disk free {pct:.1f}% ({gb:.0f} GB)", c))
        if lvl != "ok":
            print(col("      heavy targets are refused below 5% and 20 GB; reclaim with "
                      "`docker builder prune`", "d"))
    print("host ports:")
    cmd_ports(targets, args)
    print(col("doctor: PASS", "g") if ok else col("doctor: FAIL", "r"))
    return 0 if ok else 1


# ------------------------------------------------------------------- audit ---
# The lab runs deliberately vulnerable software and we get RCE inside it on
# purpose. These invariants are what keeps that inside the container, so they
# are checked mechanically rather than trusted to review.

REQUIRED = ["security_opt", "cap_drop", "pids_limit", "mem_limit"]
BANNED_CAPS = {"SYS_ADMIN", "SYS_PTRACE", "SYS_MODULE", "NET_ADMIN", "NET_RAW", "ALL"}


def _compose_docs(paths):
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                doc = yaml.safe_load(f) or {}
        except Exception as e:
            yield p, None, str(e)
            continue
        yield p, doc, None


def audit_compose(path, doc):
    """Returns a list of (level, message). level is 'fail' or 'warn'."""
    out = []
    for name, svc in (doc.get("services") or {}).items():
        where = f"{os.path.relpath(path, BASE)}::{name}"

        if svc.get("privileged"):
            out.append(("fail", f"{where}: privileged"))
        if str(svc.get("network_mode", "")).startswith("host"):
            out.append(("fail", f"{where}: network_mode host shares the host network stack"))
        for key in ("pid", "ipc", "userns_mode"):
            if str(svc.get(key, "")).startswith("host"):
                out.append(("fail", f"{where}: {key} host"))

        for v in (svc.get("volumes") or []):
            src = v.get("source") if isinstance(v, dict) else str(v).split(":")[0]
            if "docker.sock" in str(src):
                out.append(("fail", f"{where}: mounts the Docker socket, which is root on the host"))
            elif str(src).startswith("/") and not str(src).startswith(BASE):
                out.append(("warn", f"{where}: bind-mounts a host path outside the checkout ({src})"))

        bad = BANNED_CAPS & {str(c).upper().replace("CAP_", "") for c in (svc.get("cap_add") or [])}
        if bad:
            out.append(("fail", f"{where}: cap_add {', '.join(sorted(bad))}"))

        for key in REQUIRED:
            if key in svc:
                continue
            # A memory cap can legitimately arrive as deploy.resources.limits.memory,
            # which is what several upstream composes use. Compose refuses to carry
            # both with different values, so accept either.
            dep = ((svc.get("deploy") or {}).get("resources") or {}).get("limits") or {}
            if key == "mem_limit" and dep.get("memory"):
                continue
            if key == "pids_limit" and dep.get("pids"):
                continue
            out.append(("fail", f"{where}: missing {key}"))
        if "ALL" not in [str(c).upper() for c in (svc.get("cap_drop") or [])]:
            out.append(("fail", f"{where}: cap_drop must include ALL"))
        if "no-new-privileges:true" not in [str(o) for o in (svc.get("security_opt") or [])]:
            out.append(("fail", f"{where}: security_opt must set no-new-privileges:true"))

        for prt in (svc.get("ports") or []):
            spec = f"{prt.get('host_ip','')}:{prt.get('published','')}" if isinstance(prt, dict) else str(prt)
            parts = spec.split(":")
            if len(parts) < 3 or parts[0] not in ("127.0.0.1", "localhost"):
                out.append(("fail", f"{where}: port {spec} is not bound to 127.0.0.1"))

        # A service that builds here has no registry digest to pin to: the tag
        # is just a local name for whatever the Dockerfile produced. Only
        # images that are pulled can drift under us.
        img = str(svc.get("image") or "")
        if img and not svc.get("build") and "@sha256:" not in img \
                and not img.startswith("limeyard/"):
            out.append(("warn", f"{where}: {img} is not pinned by digest"))
    return out


def cmd_audit(targets, args):
    fails, warns = [], []

    paths = [t["compose_path"] for t in targets.values() if not is_fixture(t)]
    paths += [s["compose_path"] for s in load_scenarios().values()]
    for path, doc, err in _compose_docs(paths):
        if err:
            fails.append(f"{path}: unparseable ({err})")
            continue
        for level, msg in audit_compose(path, doc):
            (fails if level == "fail" else warns).append(msg)

    # The control plane is the one thing that legitimately holds the socket, so
    # it is judged by a different rule: is it authenticated.
    if not os.environ.get("LIME_TOKEN", "").strip():
        fails.append("LIME_TOKEN is unset. limed holds the Docker socket and shares a "
                     "network with the targets; without a token any popped target can "
                     "drive it. See .env.example")

    for t in targets.values():
        up = t.get("upstream") or {}
        if not up.get("author"):
            fails.append(f"{t['slug']}: no upstream.author (attribution is required)")
        if not up.get("license"):
            warns.append(f"{t['slug']}: no upstream.license recorded")

    for m in warns:
        print(col("[warn] ", "y") + m)
    for m in fails:
        print(col("[FAIL] ", "r") + m)
    print()
    if fails:
        print(col(f"audit: FAIL  ({len(fails)} failures, {len(warns)} warnings)", "r"))
        return 1
    print(col(f"audit: PASS  ({len(warns)} warnings)", "g"))
    return 0


def cmd_truth(targets, args):
    """Dump the merged answer key. This is what a scan harness should read."""
    merged = {}
    for slug, t in targets.items():
        tr = load_truth(t)
        if tr:
            merged[slug] = tr
    print(json.dumps(merged, indent=2, default=str))


def cmd_scenarios(scenarios, args):
    print(f"{_pad('SCENARIO', 14)}  {_pad('STATE', 10)}  DESCRIPTION")
    for s in scenarios.values():
        label, c = state_of(s)
        print(f"{_pad(s['slug'], 14)}  {col(_pad(label, 10), c)}  {s.get('description', '')}")


def cmd_scn_up(scenarios, args):
    ensure_networks()
    if args.name not in scenarios:
        die(f"unknown scenario '{args.name}'")
    s = scenarios[args.name]
    if missing(s):
        die(f"scenario compose missing ({s['compose_path']})")
    print(col(f"==> bringing up scenario {s['slug']}", "b"))
    dc(s, "up", "-d")
    run_setup(s)


def cmd_scn_down(scenarios, args):
    if args.name not in scenarios:
        die(f"unknown scenario '{args.name}'")
    print(col(f"==> tearing down scenario {args.name}", "b"))
    dc(scenarios[args.name], "down")


def cmd_pin(targets, args):
    import pin
    return pin.run(args.apply)


def cmd_serve(targets, args):
    from api import serve
    serve(int(args.port))


def cmd_monitor(targets, args):
    interval = args.interval or int(os.environ.get("MONITOR_INTERVAL", "30"))
    stop = {"f": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("f", True))
    print(col("limeyard control plane up. Watching every %ds." % interval, "b"))
    print(col("Drive the lab with:  ./lime <cmd>   (try: ./lime list, ./lime credits)", "d"))
    ensure_networks()
    try:
        while not stop["f"]:
            print("\n" + time.strftime("%H:%M:%S") + "  lab status")
            cmd_list(load_targets(), args)
            for _ in range(interval):
                if stop["f"]:
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    print("control plane stopped.")


def build_parser():
    p = argparse.ArgumentParser(prog="lime", description="limeyard control plane")
    sub = p.add_subparsers(dest="cmd")

    def with_targets(sp):
        sp.add_argument("names", nargs="*", help="target slugs (omit with --all/--kind)")
        sp.add_argument("--all", action="store_true", help="every target")
        sp.add_argument("--kind", choices=KINDS, help="every target of one kind")
        sp.add_argument("--heavy", action="store_true", help="include heavy targets")

    with_targets(sub.add_parser("start", help="start target(s)"))
    with_targets(sub.add_parser("stop", help="stop target(s)"))
    with_targets(sub.add_parser("restart", help="restart target(s)"))
    with_targets(sub.add_parser("pull", help="pre-pull images"))
    for n in ("list", "status"):
        sp = sub.add_parser(n, help="list targets + state")
        sp.add_argument("--kind", choices=KINDS)
    cr = sub.add_parser("credits", help="who wrote each target, and under what licence")
    cr.add_argument("--markdown", action="store_true", help="emit the README Credits section")
    sub.add_parser("ports", help="host-port map + clash check")
    ms = sub.add_parser("measure", help="print the resources block for running targets")
    ms.add_argument("names", nargs="*", help="target or scenario slugs (default: everything running)")
    su = sub.add_parser("setup", help="first run: pick what to run, see what it costs, start it")
    su.add_argument("--light", action="store_true", help="every light target and the scenarios")
    su.add_argument("--all", action="store_true", help="everything, heavy targets too")
    su.add_argument("--none", action="store_true", help="start nothing, just the panel")
    su.add_argument("--pick", help="comma separated slugs, kinds or scenario names")
    su.add_argument("--yes", action="store_true", help="do not ask before starting")
    dr = sub.add_parser("doctor", help="environment, attribution and disk checks")
    dr.add_argument("--fix", action="store_true",
                    help="repair every check that has an automatic fix, then re-check")
    sub.add_parser("audit", help="container-hardening and supply-chain invariants")
    pn = sub.add_parser("pin", help="pin images to the digest we verified")
    pn.add_argument("--apply", action="store_true", help="rewrite the compose files")
    sub.add_parser("truth", help="dump the merged answer key as JSON")
    lp = sub.add_parser("logs", help="tail a target's logs")
    lp.add_argument("name")
    lp.add_argument("-f", "--follow", action="store_true")
    sub.add_parser("scenarios", help="list scenarios")
    up = sub.add_parser("scenario-up", help="bring a scenario up")
    up.add_argument("name")
    dn = sub.add_parser("scenario-down", help="tear a scenario down")
    dn.add_argument("name")
    sv = sub.add_parser("serve", help="run the HTTP API (what the UI talks to)")
    sv.add_argument("--port", default=os.environ.get("LIMED_PORT", "7099"))
    mp = sub.add_parser("monitor", help="watch loop (the default `up` command)")
    mp.add_argument("--interval", type=int, default=0)
    return p


SCENARIO_CMDS = {"scenarios": cmd_scenarios, "scenario-up": cmd_scn_up,
                 "scenario-down": cmd_scn_down}

DISPATCH = {
    "start": cmd_start, "stop": cmd_stop, "restart": cmd_restart, "pull": cmd_pull,
    "list": cmd_list, "status": cmd_status, "credits": cmd_credits,
    "ports": cmd_ports, "setup": cmd_setup, "measure": cmd_measure, "doctor": cmd_doctor, "audit": cmd_audit, "truth": cmd_truth, "pin": cmd_pin,
    "logs": cmd_logs, "serve": cmd_serve, "monitor": cmd_monitor,
}


def main():
    if yaml is None:
        die("PyYAML missing in the control image")
    args = build_parser().parse_args()
    if not args.cmd:
        build_parser().print_help()
        sys.exit(0)
    if args.cmd in SCENARIO_CMDS:
        sys.exit(SCENARIO_CMDS[args.cmd](load_scenarios(), args) or 0)
    sys.exit(DISPATCH[args.cmd](load_targets(), args) or 0)


if __name__ == "__main__":
    main()
