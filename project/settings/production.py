"""Production settings. Requires the 'prod' extra (gunicorn, whitenoise)."""

import os

import dj_database_url
from django.core import exceptions

from .base import *  # noqa: F403

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]
if not ALLOWED_HOSTS:
    msg = "DJANGO_ALLOWED_HOSTS must be set in production."
    raise exceptions.ImproperlyConfigured(msg)
DEBUG = False

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

_database_url = os.environ.get("DATABASE_URL")
if not _database_url:
    msg = "DATABASE_URL must be set in production."
    raise exceptions.ImproperlyConfigured(msg)

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        conn_max_age=600,
        conn_health_checks=True,
    )
}
