# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""Root URL configuration. Includes bf_opencore app URLs."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("bf_opencore.urls")),
]
