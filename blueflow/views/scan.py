"""ViewSet for scans."""

import logging
from typing import ClassVar

import django_filters
from rest_framework import serializers, viewsets
from waffle.mixins import WaffleSwitchMixin

from blueflow.models import Scan

logger = logging.getLogger(__name__)


class ScanSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes scans.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="blueflow:scan-detail")
    asset = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name="blueflow:asset-detail",
    )

    class Meta:
        """Wire this serializer to a model."""

        model = Scan

        scan_fields = tuple(f.name for f in model._meta.fields)  # noqa: SLF001
        computed_fields = ("url",)

        fields = scan_fields + computed_fields


class ScanFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:
        model = Scan

        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields: ClassVar = {
            "asset": ["exact"],
        }


class ScanViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Each scan represents one "Scan" of one asset."""

    waffle_switch = "core"

    # Scan model does have 'objects'
    queryset = Scan.objects.all()
    serializer_class = ScanSerializer
    filterset_class = ScanFilter
