"""BlueFlow Group."""

import logging

from django.apps import apps
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class Group(models.Model):
    """Holds groups.

    More than one asset can belong to a group, and an asset may belong to
    one or more groups, so there's a many-to-many relationship as
    specified by the 'groups' field on Asset.
    """

    name = models.CharField(max_length=126, unique=True)
    date_added = models.DateTimeField(default=timezone.now)

    def __str__(self):  # noqa
        return f"{self.id}:{self.name}"

    @property
    def num_assets(self):
        """Return number of assets in network."""
        Asset = apps.get_model("bf_opencore", "Asset")
        return Asset.objects.filter(groups__id=self.id).count()

    @property
    def identified_statistics(self):
        """Percent identified assets."""
        Asset = apps.get_model("bf_opencore", "Asset")
        return Asset.objects.filter(groups__id=self.id).identified_statistics()


class AssetGroup(models.Model):
    """Manages relationship between Assets and Groups.

    This is a "join table" with a little bit more information.
    """

    # Use a string "Asset" instead of an object to avoid circular import
    asset = models.ForeignKey(
        "Asset", on_delete=models.CASCADE, related_name="asset_groups"
    )
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    date_added = models.DateTimeField(default=timezone.now)
    provenance = models.TextField(
        blank=True,
        null=True,
        help_text="Reason why asset was added to group: automatic, manual, etc.",
    )

    class Meta:  # noqa
        db_table = "blueflow_asset_group"
        unique_together = ("asset", "group")
