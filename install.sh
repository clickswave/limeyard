#!/usr/bin/env bash
# limeyard installer.
#
#   curl -fsSL https://raw.githubusercontent.com/clickswave/limeyard/HEAD/install.sh | bash
#
# Checks for Docker, clones the lab, writes its .env, starts the control
# plane, then hands over to `lime setup`, which shows what each target costs
# and asks what to run before anything is started.
#
#   LIMEYARD_DIR=/somewhere   where to put the checkout (default: ./limeyard)
#   LIMEYARD_REPO=<url|path>  clone source (default: the GitHub repo)
#   LIMEYARD_REF=<branch>     branch to check out (default: the repo's default branch)
#
# Anything after `bash -s --` is passed to `lime setup`, so a non-interactive
# install is:  curl ... | bash -s -- --light --yes
set -euo pipefail

REPO="${LIMEYARD_REPO:-https://github.com/clickswave/limeyard.git}"
REF="${LIMEYARD_REF:-}"
DIR="${LIMEYARD_DIR:-$PWD/limeyard}"

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m[..]\033[0m %s\n' "$*"; }
die()  { printf '  \033[31m[!!]\033[0m %s\n' "$*" >&2; exit 1; }

say "limeyard: a security testing lab. Everything in it is deliberately vulnerable."
echo "  Local use only. Every published port binds to 127.0.0.1."
echo

say "Requirements"
command -v git >/dev/null    || die "git is not installed."
ok "git $(git --version | awk '{print $3}')"
command -v docker >/dev/null || die "Docker is not installed. https://docs.docker.com/get-docker/"
if ! docker info >/dev/null 2>&1; then
  die "Docker is installed but this user cannot talk to it. Start the daemon, or add yourself to the docker group and log in again."
fi
ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')"
docker compose version >/dev/null 2>&1 || die "The docker compose plugin is missing. Install docker-compose-plugin (or Docker Desktop)."
ok "compose $(docker compose version --short)"
case "$(uname -s)" in
  Linux) ok "linux" ;;
  Darwin) warn "macOS: the panel and the 127.0.0.1 targets work; the 10.66.0.0/16 lab subnet is only reachable from inside Docker." ;;
  *) warn "$(uname -s): untested." ;;
esac
echo

say "Checkout"
if [ -d "$DIR/.git" ]; then
  ok "already at $DIR, updating"
  git -C "$DIR" fetch -q origin
  [ -n "$REF" ] && git -C "$DIR" checkout -q "$REF"
  git -C "$DIR" merge -q --ff-only "@{u}" 2>/dev/null || warn "local changes present, not fast-forwarding"
else
  if [ -n "$REF" ]; then git clone -q --branch "$REF" "$REPO" "$DIR"; else git clone -q "$REPO" "$DIR"; fi
  ok "cloned into $DIR ($(git -C "$DIR" rev-parse --abbrev-ref HEAD))"
fi
cd "$DIR"

if [ ! -f .env ]; then
  if command -v openssl >/dev/null; then TOKEN="$(openssl rand -hex 24)"
  else TOKEN="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"; fi
  { echo "LIMEYARD_DIR=$DIR"; echo "LIME_TOKEN=$TOKEN"; echo "MONITOR_INTERVAL=30"; } > .env
  ok ".env written with a fresh API token"
else
  ok ".env kept"
fi
echo

say "Control plane"
echo "  Building the daemon and the panel (a minute or two the first time)."
docker compose build -q
docker compose up -d --quiet-pull
ok "panel at http://127.0.0.1:7000"
echo

# With flags the wizard has nothing to ask. Without them it reads answers from
# the terminal, which is not stdin when this script arrives through a pipe.
if [ $# -gt 0 ]; then
  exec ./lime setup "$@" < /dev/null
elif [ -t 0 ]; then
  exec ./lime setup
elif [ -r /dev/tty ]; then
  exec ./lime setup < /dev/tty
else
  warn "no terminal to ask on; starting nothing. Run ./lime setup from $DIR."
fi
