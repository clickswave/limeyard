#!/bin/sh
# DVWA builds its schema only on a POST to setup.php carrying the create_db
# button AND the session's anti-CSRF user_token. A GET returns the page and
# changes nothing, which looks like success and leaves every login redirecting
# back to setup.php. Do it properly.
set -u
APP="http://dvwa"
JAR=/tmp/dvwa.cookies

i=0
until curl -sf -o /dev/null "$APP/setup.php" || [ $i -ge 40 ]; do i=$((i+1)); sleep 3; done
[ $i -ge 40 ] && { echo "[dvwa] web never came up"; exit 1; }

rm -f "$JAR"
TOKEN=$(curl -s -c "$JAR" "$APP/setup.php" \
        | tr '>' '\n' | grep -o "user_token' value='[^']*" | cut -d"'" -f3 | head -1)
[ -z "$TOKEN" ] && TOKEN=$(curl -s -b "$JAR" "$APP/setup.php" \
        | grep -o 'name="user_token" value="[^"]*' | cut -d'"' -f4 | head -1)

curl -s -b "$JAR" -c "$JAR" -o /dev/null \
     --data-urlencode "create_db=Create / Reset Database" \
     --data-urlencode "user_token=${TOKEN:-}" "$APP/setup.php"

# Verify against the thing that actually matters: can we log in and land
# somewhere that is not setup.php.
LT=$(curl -s -c "$JAR" -b "$JAR" "$APP/login.php" \
     | tr '>' '\n' | grep -o "user_token' value='[^']*" | cut -d"'" -f3 | head -1)
DEST=$(curl -s -b "$JAR" -c "$JAR" -o /dev/null -w '%{redirect_url}' \
       -d "username=admin&password=password&Login=Login&user_token=${LT:-}" "$APP/login.php")
case "$DEST" in
  *setup.php) echo "[dvwa] schema still missing (login redirects to setup.php)"; exit 1 ;;
  *)          echo "[dvwa] schema built, login lands on ${DEST:-index}" ;;
esac
