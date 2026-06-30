#!/usr/bin/env bash
set -e
python project/manage.py collectstatic --noinput
python project/manage.py migrate --noinput
exec "$@"
