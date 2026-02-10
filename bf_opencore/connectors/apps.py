
"""Django App Config."""

from django.apps import AppConfig


class BfOpenCoreConnectorConfig(AppConfig):  # noqa
    name = 'bf_opencore.connectors'

    def ready(self):
        """Wire up signals and other last-minute things."""
        pass