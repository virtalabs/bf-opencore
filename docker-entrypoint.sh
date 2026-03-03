#!/usr/bin/env bash
# Run migrations then exec the container command (e.g. runserver).

set -e
uv sync --frozen --no-dev
/app/.venv/bin/python project/manage.py migrate --noinput
exec "$@"