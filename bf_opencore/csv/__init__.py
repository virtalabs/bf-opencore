"""CSV import"""
import os
from collections import OrderedDict
import logging
import json
import csv as pycsv
import celery
from django.apps import apps
from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from simple_history import utils as hist_utils
from bf_opencore.celery import celery_app
from bf_opencore.utils import FieldMap, FileWrapper


logger = celery.utils.log.get_task_logger(__name__)


# Simple field mappings
DEFAULT_FIELD_MAPPING = {
    'serial_number': 'Serial',
    'mac_address': 'MAC',
    'ip_address': 'IP',
    'manufacturer': 'Manufacturer',
    'model': 'Model',
}
_DEFAULT_FIELD_NAMES = list(DEFAULT_FIELD_MAPPING.values())

CONNECTOR_SPEC = {
    "display_name": "CSV",
    "description": """Load assets from a CSV file.

By default, BlueFlow imports from columns with these names: {fieldnames}.
You can change how BlueFlow imports data by configuring the CSV connector at
its [connector settings page]({settings}).

Assets to be imported must have a value in at least one of the following
fields:

 - An IP address
 - A MAC address
 - An external key (such as a unique asset ID from another system)

When exporting data from Excel or a similar tool, choose `ASCII` or `UTF-8`
encoding.

A sample CSV file is available [here](bf_opencore/csv/sample.csv).
""".format(settings='/settings/csv/',
           fieldnames=', '.join(
               map(lambda x: '<tt>{}</tt>'.format(x),  # pylint: disable=unnecessary-lambda
                   _DEFAULT_FIELD_NAMES))),
    "kwargs": OrderedDict([
        ("filename", {
            "default": None,
            "type": FileWrapper,
            "help": "CSV file with header row",
        })
    ]),
    'settings': OrderedDict([
        ('require_network_info', {
            'type': bool,
            'default': True,
            'help': 'Import only assets with a valid MAC or IP address.',
        }),
        ('update_only', {
            'type': bool,
            'default': False,
            'help': 'Do not create new assets.  Only update existing assets.',
        }),
        ('field_mapping', {
            'type': dict,
            'default': DEFAULT_FIELD_MAPPING,
            'help': 'Mapping of BlueFlow fields to CSV column names',
        }),
    ]),
}

DEFAULTS = {k: v["default"] for k, v in CONNECTOR_SPEC["kwargs"].items()}
TYPES = {k: v["type"] for k, v in CONNECTOR_SPEC["kwargs"].items()}


def linecount(filename):
    """Return the number of lines in a file."""
    with open(filename, 'r') as filehandle:
        return sum(1 for row in filehandle)


def process_csv(ctx, filename, field_mapping, require_network_info,
                update_only):
    """Read assets from CSV file and add to database."""
    # Yea, there's a lot of branches
    # pylint: disable=too-many-branches

    Asset = apps.get_model('bf_opencore', 'Asset')
    logger.debug("Reading CSV file %s", filename)
    # The 'utf-8-sig' encoding makes us robust to Excel-exported CSV
    # files (they contain a 3-byte "byte order mark" at the beginning of
    # the file.)
    with open(filename, 'r', encoding='utf-8-sig') as csv_file:
        stats = {
            "total": 0,
            "updated": 0,
            "up-to-date": 0,
            "created": 0,
            "skipped": 0,
            "errored": 0,
        }
        for row in pycsv.DictReader(csv_file):
            stats["total"] += 1
            if stats["total"] % 1000 == 0:
                ctx.ct.inc_progress()

            # Map CSV column names to ORM fields using field mapping
            rowmap = FieldMap(row, field_mapping)

            # Ignore assets that lack MAC or IP.
            if require_network_info and not (
                    "ip_address" in rowmap.todict() and rowmap["ip_address"] or
                    "mac_address" in rowmap.todict() and rowmap["mac_address"]
            ):
                logger.debug("Skipped asset (no MAC or IP) %s", rowmap)
                stats["skipped"] += 1
                continue

            # Ignore CSV rows that would create a new asset
            if update_only:
                try:
                    Asset.objects.get_by_priority(**rowmap.todict())
                except Asset.DoesNotExist:
                    logger.debug("Skipped asset (update_only) %s", rowmap)
                    stats["skipped"] += 1
                    continue

            # Update the database.  Three possibilities:
            # 1. New asset created
            # 2. Old asset updated
            # 3. Exception due to field validation error
            #
            # The parameters for Django's update_or_create() are confusing!
            # https://docs.djangoproject.com/en/2.0/ref/models/querysets/#update-or-create
            try:
                asset, created = \
                    Asset.objects.update_or_create_by_priority(
                        defaults=rowmap.todict(),
                        **rowmap.todict(),
                    )
            except (ValidationError,
                    Asset.MultipleObjectsReturned,
                    IntegrityError) as err:
                ctx.ct.error(
                    "Error updating or creating asset: {}.\n"
                    "Raw data: {}\n"
                    "Mapped data: {}"
                    "".format(err, row, rowmap)
                )
                stats["errored"] += 1
                continue

            # Update the logs and stats
            if created == created.CREATED:
                logger.debug(
                    "Created asset %s\nRaw data: %s\nMapped data: %s",
                    asset, row, rowmap
                )
                stats["created"] += 1
            elif created == created.UPDATED:
                logger.debug(
                    "Updated asset %s. Raw data: %s. Mapped data: %s",
                    asset, row, rowmap
                )
                stats["updated"] += 1
            elif created == created.UPTODATE:
                logger.debug(
                    "Update-to-date asset %s. Raw data: %s. Mapped data: %s",
                    asset, row, rowmap
                )
                stats["up-to-date"] += 1
            else:
                logger.error(
                    "update_or_create_by_priority() returned an unrecognized"
                    "value: %s", created
                )
                stats["errored"] += 1

            # Update the asset's history.  The CSV connector is sometimes
            # called by other connectors, so we look up the connector name.
            if created:
                reason = "Created by {} import".format(ctx.ct.display_name)
            else:
                reason = "Updated by {} import".format(ctx.ct.display_name)
            hist_utils.update_change_reason(asset, reason)

        # Print stats to UI
        ctx.ct.print("Finished loading assets from CSV")
        for name in ['created', 'updated', 'up-to-date', 'skipped', 'errored']:
            value = stats[name]
            ctx.ct.print("{}{}".format(
                name.ljust(12),
                str(value).rjust(12),
            ))
        ctx.ct.print("-" * 24)
        ctx.ct.print("{}{}".format(
            "total".ljust(12),
            str(stats["total"]).rjust(12),
        ))


@celery_app.task(bind=True)
def main(ctx, filename=None, field_mapping=None, no_reset_progress=False,
         require_network_info=None, update_only=None):
    """
    Load a CSV file into the database through a field mapping.

    no_reset_progress is a performance optimization to avoid re-reading large
    files when this connector is called by another connector, e.g., TMS.
    """
    # The CSV connector is used by other connectors.  They have needs.
    # pylint: disable=too-many-arguments

    # If the caller didn't provide the following parameters, get them
    # from the settings.
    #   NOTE: if this were to be called via another connector (e.g. TMS
    # or AIMS) and they didn't explicitly pass these parameters, *their*
    # settings would still be used here - not the CSV settings.
    if require_network_info is None:
        require_network_info = ctx.ct.connector.settings['require_network_info']  # pylint: disable=line-too-long
    if update_only is None:
        update_only = ctx.ct.connector.settings['update_only']

    # Save attachment provided by the web UI, if any
    if ctx.ct.attachment:
        filename = os.path.join(
            django_settings.MEDIA_ROOT,
            ctx.ct.attachment.name,
        )
        logger.debug("Saved file %s", filename)
        if not os.path.exists(filename):
            raise ValueError("File not found: {}".format(filename))

    # Read field mapping from the database if one is not provided
    if not field_mapping:
        raise NotImplementedError("Connectors have been removed")
        Connector = apps.get_model('bf_opencore', 'Connector')
        connector = Connector.objects.get(id="csv")
        logger.debug("Settings: %s", connector.settings)
        field_mapping = connector.settings['field_mapping']

    # Set up progress bar
    if not no_reset_progress:
        nrows = linecount(filename) - 1  # Subtract 1 for header row
        ctx.ct.set_progress_total(nrows / 1000)  # Increment every 1000 assets

    # Process CSV downloaded file
    process_csv(ctx, filename, field_mapping, require_network_info,
                update_only)

    # Remove temporary file
    if ctx.ct.attachment:
        os.remove(filename)
