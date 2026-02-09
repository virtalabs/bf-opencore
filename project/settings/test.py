# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""Minimal Django settings for bf-opencore tests (pytest). Use DJANGO_SETTINGS_MODULE=project.settings.test."""

from .base import *

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]
WSGI_APPLICATION = "project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
