#!/bin/sh
# One-time bWAPP install (creates the bWAPP database), run automatically after
# `vam start`. Executes inside the manager and reaches bwapp over vuln-net.
base="http://bwapp"
i=0; while [ $i -lt 60 ]; do curl -sf -o /dev/null "$base/install.php" && break; i=$((i+1)); sleep 2; done
n=0
while [ $n -lt 10 ]; do
  if curl -s "$base/install.php?install=yes" | grep -qi "installed successfully"; then
    echo "[bwapp] installed (login bee/bug)"; exit 0
  fi
  n=$((n+1)); sleep 3
done
echo "[bwapp] install not confirmed (try /install.php manually)"; exit 0
