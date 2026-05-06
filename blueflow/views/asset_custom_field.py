"""ViewSet for asset custom field."""

import logging
import re

from rest_framework import serializers, viewsets
from rest_framework.fields import IntegerField
from waffle.mixins import WaffleSwitchMixin

from blueflow.models import Asset, AssetCustomField, AssetCustomFieldName

from .utils import ChangeReasonMixin, HugeLimitOffsetPagination

logger = logging.getLogger(__name__)


class AssetCustomFieldNameSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes custom asset field names.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    re_non_alphanum = re.compile(r"[^A-Za-z0-9]+")

    class Meta:
        """Wire this serializer to a model."""

        model = AssetCustomFieldName

        # Fields defined in the schema
        tag_fields = tuple(f.name for f in model._meta.fields)

        # Fields that are computed (not stored directly in schema)
        computed_fields = ("num_assets",)

        fields = tag_fields + computed_fields

    def validate_display_type(self, display_type_string):
        """Check against the list of display types in the model."""
        valid_display_types = [t[0] for t in AssetCustomFieldName.DISPLAY_TYPES]
        if display_type_string not in valid_display_types:
            raise serializers.ValidationError("Invalid display type")
        return display_type_string

    def validate_field_name(self, field_name):
        """Check that a field name doesn't collide with an existing one.

        Checks against:
        - Asset fields (both name and verbose_name)
        - Other AssetCustomFieldName objects
        """

        def normalize(fname):
            """Remove all non-alphanumeric chars and switch to lowercase."""
            return self.re_non_alphanum.sub("", fname.lower())

        other_fields = {normalize(f.name) for f in Asset._meta.fields}
        other_fields |= {normalize(f.verbose_name) for f in Asset._meta.fields}
        other_fields |= {
            normalize(fname)
            for fname in AssetCustomFieldName.objects.values_list(
                "field_name", flat=True
            )
        }

        if normalize(field_name) in other_fields:
            raise serializers.ValidationError(
                "Custom field name too similar to existing field name"
            )
        return field_name


class AssetCustomFieldSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes custom asset field values.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:assetcustomfield-detail"
    )
    # asset = AssetSerializer()
    field = AssetCustomFieldNameSerializer(read_only=True)
    asset_id = IntegerField()
    field_id = IntegerField()

    class Meta:
        """Wire this serializer to a model."""

        model = AssetCustomField
        fields = (
            "id",
            "url",
            "asset_id",
            "field",
            "field_id",
            "value_text",
        )


class AssetCustomFieldViewSet(
    WaffleSwitchMixin, ChangeReasonMixin, viewsets.ModelViewSet
):
    """Custom asset field (value)."""

    waffle_switch = "core"

    # AssetCustomField model does have 'objects'
    queryset = AssetCustomField.objects.all()
    serializer_class = AssetCustomFieldSerializer
    # filterset_class = AssetCustomFieldFilter
    pagination_class = HugeLimitOffsetPagination
