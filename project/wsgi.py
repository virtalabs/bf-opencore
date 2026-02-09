# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""WSGI config for the minimal Django project."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.development")

application = get_wsgi_application()
