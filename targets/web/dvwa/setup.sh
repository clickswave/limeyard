#!/bin/sh
# One-time DVWA "Create / Reset Database" (the /setup.php step), run automatically
# after `vam start`. Executes inside the manager and reaches dvwa over vuln-net.
base="http://dvwa"
i=0; while [ $i -lt 60 ]; do curl -sf -o /dev/null "$base/setup.php" && break; i=$((i+1)); sleep 2; done
n=0
while [ $n -lt 10 ]; do
  jar="$(mktemp)"
  token="$(curl -s -c "$jar" "$base/setup.php" | grep -oE '[0-9a-f]{32}' | head -1)"
  curl -s -b "$jar" -o /dev/null \
    --data-urlencode "create_db=Create / Reset Database" \
    --data-urlencode "user_token=$token" "$base/setup.php"
  if ! curl -s "$base/login.php" | grep -qi "unknown database"; then
    echo "[dvwa] database created (login admin/password)"; exit 0
  fi
  n=$((n+1)); sleep 3
done
echo "[dvwa] setup not confirmed (try /setup.php manually)"; exit 0
