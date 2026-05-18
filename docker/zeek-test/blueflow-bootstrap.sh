#!/usr/bin/env bash
# Bootstrap a real BlueFlow for the zeek-test compose:
#   1. apply migrations
#   2. flip the "core" waffle switch (every viewset 404s without it)
#   3. exec runserver
#
# Mounted into the BlueFlow container at /bootstrap.sh; no rebuild needed
# when this script changes. Auth is intentionally NOT configured -- the
# AssetViewSet has no explicit permission_classes so /api/assets/upsert/
# is open under DRF's default AllowAny.

set -euo pipefail
cd /app

echo "[blueflow-bootstrap] applying migrations..."
/app/.venv/bin/python project/manage.py migrate --noinput

echo "[blueflow-bootstrap] enabling 'core' waffle switch..."
/app/.venv/bin/python project/manage.py shell --no-startup <<'PY'
from waffle.models import Switch
Switch.objects.update_or_create(name="core", defaults={"active": True})
print("[blueflow-bootstrap] core switch active")
PY

echo "[blueflow-bootstrap] starting runserver on 0.0.0.0:8000"
exec /app/.venv/bin/python project/manage.py runserver 0.0.0.0:8000
