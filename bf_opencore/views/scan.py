"""ViewSet for scans."""

import logging

import django_filters
from rest_framework import serializers, viewsets
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import Scan

logger = logging.getLogger(__name__)


class ScanSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes scans.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="bf_opencore:scan-detail")
    asset = serializers.HyperlinkedRelatedField(
        #     many=True,
        read_only=True,
        view_name="bf_opencore:asset-detail",
    )
    connector_task = serializers.HyperlinkedRelatedField(
        #     many=True,
        read_only=True,
        view_name="bf_opencore:connectortask-detail",
    )

    class Meta:
        """Wire this serializer to a model."""

        model = Scan

        # Fields defined in the schema
        scan_fields = tuple(f.name for f in model._meta.fields)

        # Fields that are computed (not stored directly in schema)
        computed_fields = ("url",)

        fields = scan_fields + computed_fields


class ScanFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:
        model = Scan

        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields = {
            "asset": ["exact"],
        }


class ScanViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Each scan represents one "Scan" of one asset."""

    waffle_switch = "core"

    # Scan model does have 'objects'
    queryset = Scan.objects.all()
    serializer_class = ScanSerializer
    filterset_class = ScanFilter
