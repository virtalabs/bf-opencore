"""Blueflow Alert model and schema."""

import logging
from django.db import models
from django.utils import timezone
from django.urls import reverse

logger = logging.getLogger(__name__)


class Alert(models.Model):
    """Represents one alert on the UI."""

    text = models.TextField()
    external_page_url = models.URLField(null=True)
    date_created = models.DateTimeField(default=timezone.now)
    date_read = models.DateTimeField(null=True)
    date_expiration = models.DateTimeField(null=True)
    asset = models.ForeignKey(
        'Asset',
        on_delete=models.SET_NULL,
        related_name='alert_assets',
        null=True,
    )
    connector = models.ForeignKey(
        'Connector',
        on_delete=models.SET_NULL,
        related_name='alert_connectors',
        null=True,
    )
    connectortask = models.ForeignKey(
        'ConnectorTask',
        on_delete=models.SET_NULL,
        related_name='alert_connector_tasks',
        null=True,
    )
    pulsefeeditem = models.ForeignKey(
        'PulseFeedItem',
        on_delete=models.SET_NULL,
        related_name='alert_pulsefeeditems',
        null=True,
    )
    # TODO: Implement risk metrics after we have a generalized algorithm for risk scoring
    # riskmetrics = models.ForeignKey(
    #     'RiskMetrics',
    #     on_delete=models.SET_NULL,
    #     related_name='alert_risk_metrics',
    #     null=True,
    # )
    vulnerability = models.ForeignKey(
        'Vulnerability',
        on_delete=models.SET_NULL,
        related_name='alert_vulnerabilities',
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
    def link(self):
        """Compute external link from external_page_url or foreign keys.

        If external_page_url is non-null, return it.  Otherwise, try the detail
        page corresponding to each foreign key.          Return None if no link can be
        found.
        """
        if self.external_page_url:
            return self.external_page_url
        if self.asset:
            return reverse('blueflow:asset', args=[self.asset.id])
        if self.connector:
            return reverse(
                'blueflow:connector',
                args=[self.connector.id],
            )
        if self.connectortask:
            return reverse(
                'blueflow:connectortask',
                args=[self.connectortask.id],
            )
        if self.pulsefeeditem:
            return reverse(
                'blueflow:pulse',
                args=[self.pulsefeeditem.external_pulse_id],
            )
        if self.riskmetrics:
            return reverse('blueflow:report-risk')
        if self.vulnerability:
            return reverse(
                'blueflow:vulnerability',
                args=[self.vulnerability.id],
            )
        return None

    @property
    def display_text(self):
        """Show the beginning and end of long text."""
        return "{} ... {}".format(self.text[:25], self.text[-15:])

    def __str__(self):  # noqa
        return '{}:{}'.format(self.id, self.text)
