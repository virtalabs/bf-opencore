#!/usr/bin/env bash
# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.
# Run migrations then exec the container command (e.g. runserver).

set -e
# When docker-compose mounts .:/app, the host .venv may have invalid paths; ensure a working venv.
if ! /app/.venv/bin/python -c "import sys" 2>/dev/null; then
  uv sync --frozen --no-dev
fi
/app/.venv/bin/python project/manage.py migrate --noinput
exec "$@"
