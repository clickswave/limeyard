#!/bin/sh
# Seed VAmPI's demo data (GET /createdb), run automatically after `vam start`.
# Executes inside the manager and reaches vampi over vuln-net.
base="http://vampi:5000"
i=0
while [ $i -lt 40 ]; do
  if curl -sf -o /dev/null "$base/createdb"; then echo "[vampi] demo data seeded"; exit 0; fi
  i=$((i+1)); sleep 2
done
echo "[vampi] createdb not confirmed"; exit 0
