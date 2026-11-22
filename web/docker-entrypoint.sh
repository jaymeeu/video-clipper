#!/bin/sh
# Hash the team password at start-up, so .env holds a normal password rather than a
# bcrypt hash (whose "$" characters docker compose would mangle). Refuse to start without
# one: this app must never run without a login.
set -eu
: "${CLIPPERS_WEB_PASSWORD:?Set CLIPPERS_WEB_PASSWORD in .env: the web app requires a login}"
CLIPPERS_WEB_PASSWORD_HASH="$(caddy hash-password --plaintext "$CLIPPERS_WEB_PASSWORD")"
export CLIPPERS_WEB_PASSWORD_HASH
unset CLIPPERS_WEB_PASSWORD
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
