"""Django App Config."""

from django.apps import AppConfig


class BfOpenCoreConfig(AppConfig):
    name = "bf_opencore"

    def ready(self):
        """Wire up signals and other last-minute things."""
