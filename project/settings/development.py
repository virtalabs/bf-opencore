"""Development settings. Runtime config from environment variables."""

import os

import dj_database_url

from .base import *  # noqa: F403

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-not-for-production")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

CELERY_TASK_ALWAYS_EAGER = True

_database_url = os.environ.get("DATABASE_URL")
DATABASES = (
    {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=600,
            conn_health_checks=True,
        ),
    }
    if _database_url
    else {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "blueflow"),
            "USER": os.environ.get("DB_USER", "blueflow"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "blueflow"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        },
    }
)
