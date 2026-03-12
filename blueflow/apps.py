"""Django App Config."""

from django.apps import AppConfig


class BlueflowConfig(AppConfig):
    name = "blueflow"

    def ready(self):
        """Wire up signals and other last-minute things."""
