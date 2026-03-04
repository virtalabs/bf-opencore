"""Custom fields for BlueFlow Asset.

2 classes:

 - AssetCustomFieldName
 - AssetCustomField

The former contains the field names, and the latter has a foreign key to
both Asset and AssetCustomFieldName.
"""

import logging

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

logger = logging.getLogger(__name__)


class AssetCustomFieldName(models.Model):
    """Holds field name and type.

    display_type governs how this custom field is rendered to HTML. It can be:
     - text (default; render this field as an <input type="text">)
     - textarea (render this field as a <textarea>)
     - NOT YET: markdown_textarea (render this field as a <textarea> with
     markdown)
     - NOT YET: checkbox (render 'true'/'false' appropriately)
    """

    DISPLAY_TYPES = (
        ("text", "Short text field"),
        ("textarea", "Multi-line text field"),
        # 'markdown_textarea',
        # 'checkbox',
    )

    field_name = models.CharField(max_length=126, unique=True)
    display_type = models.TextField(null=False, choices=DISPLAY_TYPES, default="text")
    enabled = models.BooleanField(default=True)
    date_added = models.DateTimeField(default=timezone.now)

    def __str__(self):
        """Return a string representation of this AssetCustomFieldName."""
        return f"{self.field_name} (type={self.display_type}, enabled={self.enabled})"

    @property
    def num_assets(self):
        """Count number of assets with this custom field associated."""
        return self.asset_set.count()


class AssetCustomField(models.Model):
    """Holds Custom field values."""

    asset = models.ForeignKey(
        "Asset", on_delete=models.CASCADE, related_name="asset_custom_fields"
    )
    field = models.ForeignKey("AssetCustomFieldName", on_delete=models.CASCADE)
    value_text = models.TextField(blank=True, null=True)
    date_added = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()

    class Meta:  # noqa
        unique_together = ("asset", "field")

    def __str__(self):
        """Return a string representation of this AssetCustomField."""
        return f"({self.field.field_name})"
