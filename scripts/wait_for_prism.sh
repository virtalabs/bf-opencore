#!/usr/bin/env bash
# Wait until Prism mock accepts HTTP connections (any status code except connection failure).
set -euo pipefail

URL="${1:-http://127.0.0.1:4010/}"
CONTAINER="${2:-viper-prism}"
TIMEOUT="${3:-60}"

for _ in $(seq 1 "$TIMEOUT"); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "$URL" 2>/dev/null || true)
  if [ "$code" != "000" ]; then
    exit 0
  fi
  if ! docker ps --filter "name=^${CONTAINER}$" --filter status=running -q | grep -q .; then
    echo "Prism container ${CONTAINER} is not running" >&2
    docker logs "$CONTAINER" 2>&1 || true
    exit 1
  fi
  sleep 1
done

echo "Prism failed to respond at ${URL}" >&2
docker logs "$CONTAINER" 2>&1 || true
exit 1
