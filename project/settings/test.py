"""Minimal Django settings for blueflow tests (pytest). Use DJANGO_SETTINGS_MODULE=project.settings.test."""

import os
import tempfile

from .base import *

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]
WSGI_APPLICATION = "project.wsgi.application"

# Tests require PostgreSQL. Set DATABASE_URL (e.g. postgresql://blueflow:blueflow@localhost:5432/blueflow).
_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    raise RuntimeError(
        "Tests require PostgreSQL; set DATABASE_URL (e.g. postgresql://blueflow:blueflow@localhost:5432/blueflow)"
    )

import dj_database_url

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        conn_max_age=0,
        conn_health_checks=False,
    ),
}

MEDIA_ROOT = tempfile.mkdtemp(prefix="blueflow_test_media_")
MEDIA_URL = "/media/"
