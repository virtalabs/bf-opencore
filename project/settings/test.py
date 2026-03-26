"""Minimal Django settings for blueflow tests (pytest).

Use DJANGO_SETTINGS_MODULE=project.settings.test.
"""

import os
import tempfile

import dj_database_url

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"  # noqa: S105
DEBUG = True
ALLOWED_HOSTS = ["*"]
WSGI_APPLICATION = "project.wsgi.application"

# Tests require PostgreSQL. Set DATABASE_URL (e.g.
# postgresql://blueflow:blueflow@localhost:5432/blueflow).
_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    _msg = (
        "Tests require PostgreSQL; set DATABASE_URL"
        " (e.g. postgresql://blueflow:blueflow@localhost:5432/blueflow)"
    )
    raise RuntimeError(_msg)

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        conn_max_age=0,
        conn_health_checks=False,
    ),
}

MEDIA_ROOT = tempfile.mkdtemp(prefix="blueflow_test_media_")
MEDIA_URL = "/media/"

WAFFLE_SWITCH_DEFAULT = True
