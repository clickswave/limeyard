#!/usr/bin/env python3
"""Pin every image in the lab to the digest we actually verified.

A floating tag is a standing invitation: the publisher's account is compromised,
or an abandoned repo changes hands, and `docker compose up` quietly runs
something else. Nothing in this lab needs to float. We pin to the digest that
was pulled and tested, and re-pinning is then a deliberate, reviewable act.

  lime pin --check   report drift between the compose files and the registry
  lime pin --apply   rewrite compose files to repo:tag@sha256:...
"""
import glob
import json
import os
import re
import subprocess
import sys

IMAGE_RE = re.compile(r"^(\s*image:\s*)(['\"]?)([^'\"\s]+)(['\"]?)\s*$")


def digest_for(ref):
    """Prefer the locally pulled image, so we pin what we tested. Fall back to
    the registry for anything not pulled yet."""
    base = ref.split("@")[0]
    r = subprocess.run(["docker", "image", "inspect", base,
                        "--format", "{{json .RepoDigests}}"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        try:
            for rd in json.loads(r.stdout.strip() or "[]"):
                repo, _, dig = rd.partition("@")
                if repo == base.rsplit(":", 1)[0] or repo == base:
                    return dig
            digs = json.loads(r.stdout.strip() or "[]")
            if digs:
                return digs[0].partition("@")[2]
        except Exception:
            pass
    r = subprocess.run(["docker", "manifest", "inspect", "-v", base],
                       capture_output=True, text=True)
    if r.returncode == 0:
        try:
            d = json.loads(r.stdout)
            d = d[0] if isinstance(d, list) else d
            return d.get("Descriptor", {}).get("digest")
        except Exception:
            return None
    return None


def files():
    root = os.environ.get("LIMEYARD_DIR") or os.getcwd()
    return (sorted(glob.glob(os.path.join(root, "targets/*/*/compose.yml")))
            + sorted(glob.glob(os.path.join(root, "scenarios/*/compose.yml"))))


def run(apply_changes):
    pinned = unresolved = already = skipped = 0
    for path in files():
        out, changed = [], False
        for line in open(path):
            m = IMAGE_RE.match(line.rstrip("\n"))
            if not m:
                out.append(line)
                continue
            pre, q1, ref, q2 = m.groups()
            if "@sha256:" in ref:
                already += 1
                out.append(line)
                continue
            # Locally built and variable-interpolated images cannot be pinned.
            if ref.startswith("limeyard/") or "${" in ref:
                skipped += 1
                out.append(line)
                continue
            dig = digest_for(ref)
            if not dig:
                unresolved += 1
                print(f"  unresolved {ref}")
                out.append(line)
                continue
            out.append(f"{pre}{q1}{ref}@{dig}{q2}\n")
            pinned += 1
            changed = True
            print(f"  {ref}\n      -> {dig}")
        if changed and apply_changes:
            open(path, "w").writelines(out)
    verb = "pinned" if apply_changes else "would pin"
    print(f"\n{verb} {pinned}, already pinned {already}, "
          f"unresolvable {unresolved}, not pinnable {skipped}")
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(run("--apply" in sys.argv))
