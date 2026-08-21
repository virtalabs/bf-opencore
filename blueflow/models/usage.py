"""Per-weekday usage counters for an Asset.

Each Asset can have up to 7 Usage rows — one per day of week. Each row holds
24 integer columns (hour_00..hour_23) counting observations seen in that hour,
deduplicated by a USAGE_WINDOW_MINUTES sliding floor so that a flurry of
upserts within the same window only counts once.
"""

import datetime

from django.db import models


class DayOfWeek(models.IntegerChoices):
    """Weekday indices matching Python's datetime.weekday() convention."""

    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class Usage(models.Model):
    """Hourly observation counts for an Asset on a single weekday."""

    USAGE_WINDOW_MINUTES = 5

    asset = models.ForeignKey(
        "blueflow.Asset",
        on_delete=models.CASCADE,
        related_name="usage",
    )
    day_of_week = models.IntegerField(
        choices=DayOfWeek,
        default=DayOfWeek.MONDAY,
    )

    hour_00 = models.IntegerField(default=0)
    hour_01 = models.IntegerField(default=0)
    hour_02 = models.IntegerField(default=0)
    hour_03 = models.IntegerField(default=0)
    hour_04 = models.IntegerField(default=0)
    hour_05 = models.IntegerField(default=0)
    hour_06 = models.IntegerField(default=0)
    hour_07 = models.IntegerField(default=0)
    hour_08 = models.IntegerField(default=0)
    hour_09 = models.IntegerField(default=0)
    hour_10 = models.IntegerField(default=0)
    hour_11 = models.IntegerField(default=0)
    hour_12 = models.IntegerField(default=0)
    hour_13 = models.IntegerField(default=0)
    hour_14 = models.IntegerField(default=0)
    hour_15 = models.IntegerField(default=0)
    hour_16 = models.IntegerField(default=0)
    hour_17 = models.IntegerField(default=0)
    hour_18 = models.IntegerField(default=0)
    hour_19 = models.IntegerField(default=0)
    hour_20 = models.IntegerField(default=0)
    hour_21 = models.IntegerField(default=0)
    hour_22 = models.IntegerField(default=0)
    hour_23 = models.IntegerField(default=0)

    last_window_started_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("asset", "day_of_week"),
                name="usage_unique_per_asset_per_day",
            ),
        )

    def __str__(self) -> str:
        return f"Usage(asset={self.asset_id}, day={DayOfWeek(self.day_of_week).label})"

    @classmethod
    def floor_to_window(cls, when: datetime.datetime) -> datetime.datetime:
        """Floor a datetime down to its USAGE_WINDOW_MINUTES bucket boundary."""
        discard = datetime.timedelta(
            minutes=when.minute % cls.USAGE_WINDOW_MINUTES,
            seconds=when.second,
            microseconds=when.microsecond,
        )
        return when - discard
