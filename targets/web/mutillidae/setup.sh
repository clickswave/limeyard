#!/bin/sh
# Mutillidae ships an empty database and builds its schema on demand, so this
# hook is load-bearing rather than cosmetic: without it every database-backed
# page 302s to database-offline.php.
#
# index.php redirects on ANY uncaught exception, so "database offline" is what
# you see whether the database is missing, still starting, or the LDAP
# directory is unreachable. That makes a blind one-shot curl useless. We wait
# for the app, run the build, then verify against a page that actually reads
# the database, and only give up after a real timeout.
set -u
APP="http://mutillidae"

say() { echo "  mutillidae: $*"; }

# 1. Wait for Apache.
i=0
until curl -sf -o /dev/null "$APP/index.php" || [ "$i" -ge 40 ]; do
  i=$((i + 1)); sleep 3
done
[ "$i" -ge 40 ] && { say "web never came up"; exit 1; }

# 2. Build the schema, retrying: the database container may still be starting,
#    and the build is idempotent (it drops and recreates).
built=0
i=0
while [ "$i" -lt 10 ]; do
  if curl -sf --max-time 120 "$APP/set-up-database.php" 2>/dev/null | grep -q "Successfully inserted data into"; then
    built=1; break
  fi
  i=$((i + 1)); sleep 5
done
[ "$built" = 1 ] || { say "schema build never succeeded"; exit 1; }

# 3. Verify the app serves. index.php calls MySQLHandler::databaseAvailable()
#    on EVERY request and redirects to database-offline.php when it fails, so a
#    200 on any public page is proof the database bootstrap worked.
#
#    Use a public page deliberately. Most of the interesting pages (user-info,
#    dns-lookup, add-to-your-blog) require a login and answer 302 to
#    index.php?page=login.php, which is indistinguishable from the
#    database-offline redirect unless you read the Location header.
i=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' "$APP/index.php?page=login.php")" = "200" ] || [ "$i" -ge 20 ]; do
  i=$((i + 1)); sleep 3
done
[ "$i" -ge 20 ] && { say "schema built but the app is not serving"; exit 1; }
say "schema built and serving"
