"""Django App Config."""

from django.apps import AppConfig

import blueflow.spectacular  # noqa: F401 — register drf-spectacular extensions.


class BlueflowConfig(AppConfig):
    """BlueFlow application bootstrap."""

    name = "blueflow"

    def ready(self):
        """Wire up signals and other last-minute things."""
