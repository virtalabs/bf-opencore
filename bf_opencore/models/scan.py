"""BlueFlow scan.

Links a "ConnectorTask" to an asset.
"""

import logging
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Scan(models.Model):
    """Indicates a scan.

    Really just a join table between Asset and ConnectorTask.
    """

    asset = models.ForeignKey("Asset", on_delete=models.CASCADE)
    connector_task = models.ForeignKey("connectors.ConnectorTask",
                                       on_delete=models.CASCADE)
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

    class Meta:  # noqa
        unique_together = ("asset", "connector_task")
