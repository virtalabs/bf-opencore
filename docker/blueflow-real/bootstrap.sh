#!/usr/bin/env bash
# Bootstrap a real BlueFlow instance for the Zeek harness.
#
# 1. uv sync + migrate
# 2. enable the "core" waffle switch — without it every viewset 404s
# 3. create a test user + mint an API token
# 4. persist token + URL to /shared/ (for the sidecar) and /logs/ (host-visible)
# 5. touch /shared/blueflow-ready so the zeek container can proceed
# 6. exec the CMD passed by the Dockerfile (runserver by default)
#
# Mounted into the container via docker-compose; never built into the image.

set -euo pipefail
cd /app

echo "[bootstrap] uv sync + migrate..."
uv sync --frozen --no-dev
/app/.venv/bin/python project/manage.py migrate --noinput

echo "[bootstrap] enable core waffle switch + mint API token..."
TOKEN=$(/app/.venv/bin/python project/manage.py shell --no-startup -c "
from waffle.models import Switch
Switch.objects.update_or_create(name='core', defaults={'active': True})
from django.contrib.auth.models import User
user, _ = User.objects.get_or_create(
    username='zeek-harness', defaults={'is_staff': True}
)
from rest_framework.authtoken.models import Token
token, _ = Token.objects.get_or_create(user=user)
print(token.key)
" 2>/dev/null | tail -1)

if [ -z "$TOKEN" ]; then
    echo "[bootstrap] FAIL: token mint produced empty output" >&2
    exit 1
fi

echo "[bootstrap] persist token + URL..."
mkdir -p /shared /logs
printf '%s' "$TOKEN"                       > /shared/api-token
printf '%s' "$TOKEN"                       > /logs/api-token
printf '%s' "http://blueflow-real:8000"    > /shared/api-url
touch /shared/blueflow-ready

echo "[bootstrap] complete. Token (last 6): ...${TOKEN: -6}"
echo "[bootstrap] handing off to: $*"
exec "$@"
