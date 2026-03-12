"""BlueFlow Tag."""

import logging

from django.apps import apps
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

logger = logging.getLogger(__name__)


class Tag(models.Model):
    """Holds tags.

    Tags are associated with one or more assets, and an asset may have
    one or more tags, so there's a many-to-many relationship as
    specified by the 'tags' field on Asset.
    """

    name = models.CharField(max_length=126, unique=True)
    color = models.CharField(max_length=7)
    date_added = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.id}:{self.name}:{self.color}"

    @property
    def num_assets(self):
        """Calculate number of assets with this tag."""
        Asset = apps.get_model("blueflow", "Asset")
        asset_qset = Asset.objects.filter(tags__id=self.id)
        return asset_qset.count


class AssetTag(models.Model):
    """Manages relationship between Assets and Tags.

    This is a "join table" with a little bit more information.
    """

    # Use a string "Asset" instead of an object to avoid circular import
    asset = models.ForeignKey(
        "Asset", on_delete=models.CASCADE, related_name="asset_tags"
    )
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    date_added = models.DateTimeField(default=timezone.now)
    provenance = models.TextField(
        blank=True,
        null=True,
        help_text="Reason why tag was added to Asset: automatic, manual, etc.",
    )

    history = HistoricalRecords()

    class Meta:
        db_table = "blueflow_asset_tag"
        unique_together = ("asset", "tag")
