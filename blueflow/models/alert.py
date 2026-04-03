"""Blueflow Alert model and schema."""

import logging

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Alert(models.Model):
    """Represents one alert on the UI."""

    text = models.TextField()
    external_page_url = models.URLField(null=True)
    date_created = models.DateTimeField(default=timezone.now)
    date_read = models.DateTimeField(null=True)
    date_expiration = models.DateTimeField(null=True)
    asset = models.ForeignKey(
        "Asset",
        on_delete=models.SET_NULL,
        related_name="alert_assets",
        null=True,
    )
    pulsefeeditem = models.ForeignKey(
        "PulseFeedItem",
        on_delete=models.SET_NULL,
        related_name="alert_pulsefeeditems",
        null=True,
    )
    # TODO: Implement risk metrics after we have a generalized algorithm
    # for risk scoring
    # riskmetrics = models.ForeignKey(
    #     'RiskMetrics',
    #     on_delete=models.SET_NULL,
    #     related_name='alert_risk_metrics',
    #     null=True,
    # )
    vulnerability = models.ForeignKey(
        "Vulnerability",
        on_delete=models.SET_NULL,
        related_name="alert_vulnerabilities",
        null=True,
    )

    @property
    def status(self):
        """Convert date fields to read status.

        NOTE: if this function changes, you'll also need to change code in
        api/views/alert.py::AlertViewSet::list().
        """
        if self.date_read is not None:
            return "read"
        return "unread"

    @property
    def display_text(self):
        """Show the beginning and end of long text."""
        return f"{self.text[:25]} ... {self.text[-15:]}"

    @property
    def riskmetrics(self) -> None:
        """Return the riskmetrics of the alert.
        Implementation is TBD the generalized algo
        """
        return None

    def __str__(self):
        return f"{self.id}:{self.text}"
