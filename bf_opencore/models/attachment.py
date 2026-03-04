"""BlueFlow AssetAttachment."""

import logging

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

logger = logging.getLogger(__name__)


class Attachment(models.Model):
    """Contain a file, that's been uploaded as an attachment to an Asset."""

    name = models.TextField(null=True, blank=True)
    file_name = models.TextField()  # Original filename
    file = models.FileField(upload_to="attachments")  # upload_to is a folder
    asset = models.ForeignKey("Asset", on_delete=models.CASCADE, null=True)
    manufacturer = models.TextField(blank=True, null=True)
    model = models.TextField(blank=True, null=True)
    date_added = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()

    @property
    def added_by(self):
        """Return user.id of original creator."""
        # There can be only one 'creation', so we could have used
        # 'get()' but let's be robust.
        hist_created = self.history.filter(history_type="+").first()
        return hist_created.history_user.username

    @property
    def display_name(self):
        """Prefer to show a user-entered name, otherwise filename."""
        if self.name:
            return self.name
        return self.file_name

    @property
    def size_bytes(self):
        """Return the file size in bytes."""
        try:
            fsize = self.file.size
        except FileNotFoundError:
            fsize = None
        return fsize
