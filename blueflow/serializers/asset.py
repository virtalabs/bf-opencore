import typing

import netaddr
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from blueflow import models

from .interface import NetworkInterfaceSerializer


class AssetServiceSerializer(serializers.Serializer):
    """A single ``(port, protocol)`` observation on an asset."""

    port = serializers.IntegerField(
        min_value=models.PORT_MIN, max_value=models.PORT_MAX
    )
    protocol = serializers.CharField(
        min_length=1,
        max_length=models.PROTOCOL_MAX_LENGTH,
        allow_blank=False,
    )
    name = serializers.CharField(allow_blank=True, required=False, default="")


class AssetUpsertSerializer(serializers.Serializer):
    """Input serializer for PUT /api/assets/upsert/.

    Validates scanner payloads before create-or-update.
    Only includes fields that passive scanners are expected to send.
    """

    mac_address = serializers.CharField(required=True, allow_blank=False)
    ip_address = serializers.IPAddressField(
        required=False, allow_blank=False, allow_null=True
    )
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    hostname = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    manufacturer = serializers.CharField(
        required=True, allow_blank=False, allow_null=False
    )
    model = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    serial_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    os = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    app_sw_version = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    external_keys = serializers.JSONField(required=False, allow_null=True)
    services = AssetServiceSerializer(many=True, required=False)

    def validate_mac_address(self, mac_address: str) -> netaddr.EUI:
        try:
            mac = netaddr.EUI(mac_address)
            return mac
        except netaddr.AddrConversionError as e:
            raise serializers.ValidationError from e
        except netaddr.AddrFormatError as e:
            raise serializers.ValidationError from e

    def validate_services(
        self, services: list[dict[str, int | str]]
    ) -> list[dict[str, int | str]]:
        """Deduplicate ``(port, protocol)`` pairs."""
        seen: set[tuple[int, str]] = set()
        deduped: list[dict[str, int | str]] = []
        for s in services:
            key = (s["port"], s["protocol"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(s)
        return deduped


class BulkAssetUpdateListSerializer(serializers.ListSerializer):
    """Validates the *batch envelope* for ``PATCH /api/assets/bulk_update/``.

    Per-item field validation and the id-to-instance lookup stay in the view;
    this enforces only the cross-item constraint that ids are unique. Runs after
    every child item has validated, so ``item["id"]`` is guaranteed present.
    """

    def validate(self, attrs: list[dict]) -> list[dict]:
        """Reject a batch containing the same id more than once."""
        ids: list[int] = [item["id"] for item in attrs]
        seen: set[int] = set()
        for i in ids:
            if i in seen:
                raise serializers.ValidationError(
                    {"detail": f"Duplicate id in request: {i}."}
                )
            seen.add(i)
        return attrs


class BulkAssetUpdateSerializer(serializers.Serializer):
    """One item in a bulk-update batch: requires an ``id`` to target an asset.

    Other asset fields pass through untouched here — they are validated and
    applied per-item by :class:`AssetSerializer` in the view. This serializer
    exists only to gate the batch envelope (list shape, id presence, id
    uniqueness) through DRF's standard ``ValidationError`` pathway, so every
    asset write endpoint surfaces validation failures uniformly.
    """

    id = serializers.IntegerField(required=True)

    class Meta:
        """Route ``many=True`` instances through the duplicate-id check."""

        list_serializer_class = BulkAssetUpdateListSerializer


# Usage field schema. Index follows Python's datetime.weekday() / ISO 8601:
# 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday.
# Each entry maps hour-of-day (0-23, JSON-string-coerced) to non-negative count.
# Hours with zero observations are omitted. The schema is inlined here (rather
# than a named Usage component) because it's small and used in exactly one place.
_USAGE_FIELD_SCHEMA = {
    "type": "array",
    "minItems": 7,
    "maxItems": 7,
    "items": {
        "type": "object",
        "additionalProperties": {"type": "integer", "minimum": 0},
    },
    "example": [
        {"9": 1, "10": 12, "11": 8, "14": 3, "15": 5},  # 0 = Monday
        {"9": 1, "10": 8, "11": 15},  # 1 = Tuesday
        {"9": 2, "14": 5},  # 2 = Wednesday
        {"10": 6, "11": 9, "13": 4},  # 3 = Thursday
        {"9": 1, "13": 2},  # 4 = Friday
        {},  # 5 = Saturday
        {},  # 6 = Sunday
    ],
}


class AssetRequestSerializer(serializers.ModelSerializer):
    """Serializes assets."""

    last_updated = serializers.DateTimeField(read_only=True, allow_null=True)
    usage = serializers.SerializerMethodField(
        help_text=(
            "Usage pattern: 7-element array of hour-of-day to observation-count "
            "maps. Index is 0-based with Monday first — 0=Monday, 1=Tuesday, "
            "2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday. Hour keys "
            "are JSON-string-coerced integers 0-23; counts are non-negative; "
            "hours with zero observations are omitted from the response."
        ),
    )
    manufacturer = serializers.CharField()

    class Meta:
        """Wire this serializer to a model."""

        model: typing.ClassVar = models.Asset
        fields: typing.ClassVar = "__all__"
        read_only_fields: typing.ClassVar = ["oui_manufacturer"]

    @extend_schema_field(_USAGE_FIELD_SCHEMA)
    def get_usage(self, obj):
        days = [{} for _ in range(7)]
        for usage in obj.usage.all():
            bucket = days[usage.day_of_week]
            for hour in range(24):
                count = getattr(usage, f"hour_{hour:02d}")
                if count > 0:
                    bucket[str(hour)] = count
        return days


class AssetResponseSerializer(serializers.ModelSerializer):
    """Serializes assets."""

    interface = NetworkInterfaceSerializer(allow_null=False)
    last_updated = serializers.DateTimeField(read_only=True, allow_null=True)
    usage = serializers.SerializerMethodField(
        help_text=(
            "Usage pattern: 7-element array of hour-of-day to observation-count "
            "maps. Index is 0-based with Monday first — 0=Monday, 1=Tuesday, "
            "2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday. Hour keys "
            "are JSON-string-coerced integers 0-23; counts are non-negative; "
            "hours with zero observations are omitted from the response."
        ),
    )
    manufacturer = serializers.CharField()
    oui_manufacturer = serializers.CharField()

    class Meta:
        """Wire this serializer to a model."""

        model: typing.ClassVar = models.Asset
        fields: typing.ClassVar = "__all__"
        read_only_fields: typing.ClassVar = ["oui_manufacturer"]

    @extend_schema_field(_USAGE_FIELD_SCHEMA)
    def get_usage(self, obj):
        days = [{} for _ in range(7)]
        for usage in obj.usage.all():
            bucket = days[usage.day_of_week]
            for hour in range(24):
                count = getattr(usage, f"hour_{hour:02d}")
                if count > 0:
                    bucket[str(hour)] = count
        return days
