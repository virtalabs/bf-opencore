"""Joint table for assets and vulns."""

from rest_framework import serializers, viewsets
from rest_framework.fields import IntegerField
from waffle.mixins import WaffleSwitchMixin

from blueflow.models import AssetTag

from .tag import TagSerializer
from .utils import ChangeReasonMixin, HugeLimitOffsetPagination


class AssetTagSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes AssetTag objects."""

    url = serializers.HyperlinkedIdentityField(view_name="blueflow:assettag-detail")
    tag = TagSerializer(read_only=True)
    asset_id = IntegerField()
    tag_id = IntegerField()

    class Meta:
        model = AssetTag
        fields = (
            "id",
            "asset_id",
            "tag_id",
            "date_added",
            "provenance",
            # Fields that are created (not stored directly in schema)
            "tag",
            "url",
        )


class AssetTagViewSet(WaffleSwitchMixin, ChangeReasonMixin, viewsets.ModelViewSet):
    """An AssetTag links a tag to an asset."""

    waffle_switch = "core"

    # AssetTag model does have 'objects'
    queryset = AssetTag.objects.all()
    serializer_class = AssetTagSerializer
    pagination_class = HugeLimitOffsetPagination
