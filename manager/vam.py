#!/usr/bin/env python3
"""vam - the vuln_apps manager.

Drives a fleet of intentionally-vulnerable apps. Each app is defined by a
skeleton folder under apps/<slug>/ (an app.yml manifest + a compose.yml) and is
run as its OWN isolated `docker compose` project, so every app gets its own
network, volumes and database - two apps that both use Postgres never share one.
Only the app's web/target port is published (to 127.0.0.1); databases and
internal tiers are never bound to the host.

Dev/testing tool. It talks to the host Docker daemon via the mounted socket.
"""
import argparse
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
BASE = os.environ.get("VULN_APPS_DIR") or os.path.dirname(HERE)
APPS_DIR = os.path.join(BASE, "apps")
NETWORK = os.environ.get("VULN_NET", "vuln-net")
PREFIX = "vuln-"

_TTY = sys.stdout.isatty()
_COL = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m",
        "b": "\033[1;34m", "d": "\033[2m", "x": "\033[0m"}


def col(s, c):
    return f"{_COL[c]}{s}{_COL['x']}" if _TTY and c in _COL else s


def die(msg):
    print(col("error: " + msg, "r"), file=sys.stderr)
    sys.exit(1)


def load_apps():
    """Discover apps from apps/<slug>/. Returns {slug: meta}."""
    apps = {}
    if not os.path.isdir(APPS_DIR):
        return apps
    for slug in sorted(os.listdir(APPS_DIR)):
        d = os.path.join(APPS_DIR, slug)
        if not os.path.isdir(d):
            continue
        meta = {}
        mp = os.path.join(d, "app.yml")
        if os.path.exists(mp) and yaml:
            try:
                with open(mp) as f:
                    meta = yaml.safe_load(f) or {}
            except Exception as e:
                print(col(f"warning: {slug}/app.yml parse error: {e}", "y"), file=sys.stderr)
                meta = {}
        meta.setdefault("name", slug)
        meta["slug"] = slug
        meta["dir"] = d
        comp = meta.get("compose")
        if meta.get("repo"):
            # Repo-backed app: source is fetched at runtime into <app>/src,
            # never vendored here. compose is the path WITHIN the repo.
            meta["src_dir"] = os.path.join(d, "src")
            meta["compose_path"] = os.path.join(meta["src_dir"], comp or "docker-compose.yml")
        elif comp:
            meta["compose_path"] = comp if os.path.isabs(comp) else os.path.normpath(os.path.join(d, comp))
        else:
            meta["compose_path"] = os.path.join(d, "compose.yml")
        meta["project"] = meta.get("project", PREFIX + slug)
        apps[slug] = meta
    return apps


def dc(app, *args, capture=False):
    """Run `docker compose` for one app's project."""
    cmd = ["docker", "compose", "-p", app["project"], "-f", app["compose_path"], *args]
    cwd = os.path.dirname(app["compose_path"]) or None
    if capture:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return subprocess.run(cmd, cwd=cwd)


def ensure_network():
    r = subprocess.run(["docker", "network", "inspect", NETWORK],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        subprocess.run(["docker", "network", "create", NETWORK], stdout=subprocess.DEVNULL)


def fetched(app):
    return not app.get("repo") or os.path.isdir(os.path.join(app.get("src_dir", ""), ".git"))


def ensure_src(app):
    """Clone a repo-backed app's source on first use. Returns True if ready."""
    if fetched(app):
        return True
    repo, src = app["repo"], app["src_dir"]
    print(col(f"  fetching {app['slug']} from {repo}", "d"))
    cmd = ["git", "clone", "--depth", "1"]
    if app.get("ref"):
        cmd += ["--branch", str(app["ref"])]
    cmd += [repo, src]
    return subprocess.run(cmd).returncode == 0


def containers(app):
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter",
         f"label=com.docker.compose.project={app['project']}",
         "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"],
        capture_output=True, text=True)
    rows = []
    for line in r.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append(tuple(parts))
    return rows


def state_of(app):
    cs = containers(app)
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


def missing(app):
    if not os.path.exists(app["compose_path"]):
        return True
    return False


def resolve(apps, names, all_flag, heavy):
    if all_flag:
        return [a for a in apps.values() if not (a.get("heavy") and not heavy)]
    if not names:
        die("name one or more apps, or pass --all  (see: vam list)")
    out = []
    for n in names:
        if n not in apps:
            die(f"unknown app '{n}'  (see: vam list)")
        out.append(apps[n])
    return out


def _pad(s, w):
    return s + " " * max(0, w - len(s))


# ---------------------------------------------------------------- commands ---
def cmd_list(apps, args):
    print(f"{_pad('APP', 13)}  {_pad('STATE', 10)}  {_pad('URL', 30)}  DESCRIPTION")
    for a in apps.values():
        label, c = state_of(a)
        tag = " [heavy]" if a.get("heavy") else (" [external]" if a.get("external") else "")
        print(f"{_pad(a['slug'], 13)}  {col(_pad(label, 10), c)}  "
              f"{_pad(a.get('url', '-'), 30)}  {a.get('description', '')}{col(tag, 'd')}")


cmd_status = cmd_list  # same view


def cmd_start(apps, args):
    ensure_network()
    targets = resolve(apps, args.names, args.all, args.heavy)
    for a in targets:
        if a.get("repo") and not ensure_src(a):
            print(col(f"  FAILED to fetch {a['slug']} source", "r"))
            continue
        if missing(a):
            print(col(f"  skip {a['slug']}: compose not found ({a['compose_path']})", "y"))
            continue
        print(col(f"==> starting {a['slug']}  ({a['name']})", "b"))
        if dc(a, "up", "-d").returncode != 0:
            print(col(f"  FAILED: {a['slug']}", "r"))
    if args.all:
        skipped = [a["slug"] for a in apps.values() if a.get("heavy") and not args.heavy]
        if skipped:
            print(col(f"note: skipped heavy apps ({', '.join(skipped)}); add --heavy to include", "d"))
    print()
    cmd_list(apps, args)


def cmd_stop(apps, args):
    targets = resolve(apps, args.names, args.all, True)  # --all stops heavy too
    for a in targets:
        if missing(a):
            continue
        print(col(f"==> stopping {a['slug']}", "b"))
        dc(a, "down")


def cmd_restart(apps, args):
    cmd_stop(apps, args)
    cmd_start(apps, args)


def cmd_pull(apps, args):
    for a in resolve(apps, args.names, args.all, args.heavy):
        if a.get("repo"):
            if fetched(a):
                print(col(f"==> updating {a['slug']} source", "b"))
                subprocess.run(["git", "-C", a["src_dir"], "pull", "--ff-only"])
            else:
                ensure_src(a)
        if missing(a):
            continue
        print(col(f"==> pulling {a['slug']} images", "b"))
        dc(a, "pull")


def cmd_logs(apps, args):
    if args.name not in apps:
        die(f"unknown app '{args.name}'")
    dc(apps[args.name], "logs", *(["-f"] if args.follow else ["--tail", "200"]))


def _host_ports(app):
    if not (yaml and os.path.exists(app["compose_path"])):
        return []
    try:
        with open(app["compose_path"]) as f:
            doc = yaml.safe_load(f) or {}
    except Exception:
        return []
    out = []
    for sname, svc in (doc.get("services") or {}).items():
        for p in (svc.get("ports") or []):
            if isinstance(p, dict):
                if p.get("published"):
                    out.append((str(p["published"]), sname))
            else:
                parts = str(p).split(":")
                if len(parts) == 3:
                    out.append((parts[1], sname))
                elif len(parts) == 2:
                    out.append((parts[0], sname))
    return out


def cmd_ports(apps, args):
    seen = {}
    for a in apps.values():
        for hp, svc in _host_ports(a):
            seen.setdefault(hp, []).append(f"{a['slug']}/{svc}")
    clash = False
    for hp in sorted(seen, key=lambda x: int(x) if x.isdigit() else 0):
        owners = seen[hp]
        if len(owners) > 1:
            clash = True
        line = f"  127.0.0.1:{_pad(hp, 6)} -> {', '.join(owners)}"
        print(col(line + "   CLASH", "r") if len(owners) > 1 else line)
    print(col("PORT CLASH DETECTED", "r") if clash else col("no host-port clashes", "g"))
    return clash


def cmd_doctor(apps, args):
    dok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    print(("[ok] " if dok else "[!!] ") + "docker daemon reachable")
    nok = subprocess.run(["docker", "network", "inspect", NETWORK],
                         capture_output=True).returncode == 0
    print(f"[{'ok' if nok else '..'}] shared network '{NETWORK}' "
          + ("present" if nok else "absent (created on first start)"))
    for a in apps.values():
        if missing(a):
            if a.get("repo"):
                print(f"[..] {a['slug']}: source not fetched yet (git clone on start)")
            else:
                print(f"[!!] {a['slug']}: compose missing ({a['compose_path']})")
    print("host ports:")
    cmd_ports(apps, args)


def cmd_monitor(apps, args):
    interval = args.interval or int(os.environ.get("MONITOR_INTERVAL", "30"))
    stop = {"f": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("f", True))
    print(col(f"vuln_apps_manager up. Watching every {interval}s.", "b"))
    print(col("Drive the fleet with:  docker compose run --rm vuln_apps_manager <cmd>", "d"))
    print(col("  e.g.  ... start --all  |  ... status  |  ... stop --all", "d"))
    ensure_network()
    try:
        while not stop["f"]:
            print("\n" + time.strftime("%H:%M:%S") + "  fleet status")
            cmd_list(load_apps(), args)
            for _ in range(interval):
                if stop["f"]:
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    print("manager stopped.")


def build_parser():
    p = argparse.ArgumentParser(prog="vam", description="vuln_apps manager")
    sub = p.add_subparsers(dest="cmd")

    def with_targets(sp):
        sp.add_argument("names", nargs="*", help="app slugs (omit with --all)")
        sp.add_argument("--all", action="store_true", help="every app")
        sp.add_argument("--heavy", action="store_true", help="include heavy apps with --all")

    with_targets(sub.add_parser("start", help="start app(s)"))
    with_targets(sub.add_parser("stop", help="stop app(s)"))
    with_targets(sub.add_parser("restart", help="restart app(s)"))
    with_targets(sub.add_parser("pull", help="pre-pull images"))
    sub.add_parser("list", aliases=["ls"], help="list apps + state")
    sub.add_parser("status", aliases=["ps"], help="fleet status")
    sub.add_parser("ports", help="host-port map + clash check")
    sub.add_parser("doctor", help="environment + port checks")
    lp = sub.add_parser("logs", help="tail an app's logs")
    lp.add_argument("name")
    lp.add_argument("-f", "--follow", action="store_true")
    mp = sub.add_parser("monitor", help="watch loop (the default `up` command)")
    mp.add_argument("--interval", type=int, default=0)
    return p


DISPATCH = {
    "start": cmd_start, "stop": cmd_stop, "restart": cmd_restart, "pull": cmd_pull,
    "list": cmd_list, "ls": cmd_list, "status": cmd_status, "ps": cmd_status,
    "ports": cmd_ports, "doctor": cmd_doctor, "logs": cmd_logs, "monitor": cmd_monitor,
}


def main():
    if yaml is None:
        die("PyYAML missing in the manager image")
    args = build_parser().parse_args()
    if not args.cmd:
        build_parser().print_help()
        sys.exit(0)
    DISPATCH[args.cmd](load_apps(), args)


if __name__ == "__main__":
    main()
