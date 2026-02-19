
"""Create or update connectors."""

from django.core.management.base import BaseCommand
import bf_opencore
from bf_opencore.models import Connector

# TODO: review this when we have mock data to import

class Command(BaseCommand):  # noqa: D101
    """Django manage.py sub command creates connectors."""

    help = 'Create or update connectors.'
    # It offends my sensibilities that we can't supply the help with a
    # docstring...

    def handle(self, *args, **options):  # noqa: D102
        verbosity = options.pop('verbosity', 2)
        if verbosity > 1:
            print("create_connectors")
        if verbosity > 2:
            print("unused args='{}', options='{}'".format(args, options))
        create_connectors(verbosity)


def create_connectors(verbosity=0):
    """Create or update connectors."""
    if verbosity > 0:
        print("Updating connector table ...")
    for connector in bf_opencore.CONNECTORS:
        if verbosity > 2:
            print(connector.name)
        module = getattr(bf_opencore, connector.name)
        default_settings = {setting_name: value['default']
                            for setting_name, value in
                            module.CONNECTOR_SPEC['settings'].items()}
        connector, created = Connector.objects.get_or_create(
            id=connector.name,
            defaults={
                'celery_task_name': module.main.name,
                'enabled': connector.default_enabled,
                'settings': default_settings,
            }
        )

        # Update settings if necessary, add risk factors
        if not created:
            updated_settings = connector.update_or_create_settings()
        connector.update_or_create_risk_factors()

        if created and verbosity > 0:
            print("Created {}".format(connector))
        elif not created and updated_settings and verbosity > 0:
            print("Updated {}".format(connector))
