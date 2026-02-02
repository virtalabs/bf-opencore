# Copyright (C) 2017-2026 Virta Laboratories, Inc.  All rights reserved.

"""Django App Config."""

from django.apps import AppConfig


class BlueflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "blueflow"
    verbose_name = "BlueFlow Core"

    def ready(self):
        # Open-core initialization
        pass
