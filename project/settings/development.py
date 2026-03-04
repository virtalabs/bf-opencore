"""Development settings. Runtime config from environment variables."""

import os

from .base import *

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
STATIC_ROOT = os.environ.get("STATIC_ROOT", "/app/staticfiles")
STATIC_URL = os.environ.get("STATIC_URL", "/static/")

# Database: prefer DATABASE_URL (e.g. dj-database-url), else DB_* env vars
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=600,
            conn_health_checks=True,
        ),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "blueflow"),
            "USER": os.environ.get("DB_USER", "blueflow"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "blueflow"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        },
    }
