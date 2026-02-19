#!/usr/bin/env bash
# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.
# Run migrations then exec the container command (e.g. runserver).

set -e
uv sync --frozen --no-dev
/app/.venv/bin/python project/manage.py migrate --noinput
exec "$@"