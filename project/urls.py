# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""Root URL configuration. Includes bf_opencore app URLs."""

from django.urls import path, include

urlpatterns = [
    path("api/", include("bf_opencore.urls")),
]
