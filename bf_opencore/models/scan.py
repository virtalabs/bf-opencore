"""BlueFlow scan"""

import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


# TODO: do we still need this model now that Connectors have been removed?
class Scan(models.Model):
    """Indicates a scan.

    Really just a join table between Asset and IntegrationTask.
    """

    asset = models.ForeignKey("Asset", on_delete=models.CASCADE)
    num_vulnerabilities = models.IntegerField()
    num_plugins = models.IntegerField()
    provenance = models.TextField(
        blank=True, null=True,
        help_text="Tool that scanned Asset",
        )
    external_url = models.TextField(
        blank=True, null=True,
        help_text="URL to results page of tool that scanned Asset",
        )
    date_scanned = models.DateTimeField()
    date_added = models.DateTimeField(default=timezone.now)
