"""ViewSet for asset custom field."""

import logging
import re
from rest_framework import viewsets, serializers
from rest_framework.fields import IntegerField
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import AssetCustomFieldName, AssetCustomField, Asset
from .utils import HugeLimitOffsetPagination, ChangeReasonMixin

logger = logging.getLogger(__name__)

class AssetCustomFieldNameSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes custom asset field names.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="api:assetcustomfieldname-detail")
    # page_url = serializers.HyperlinkedIdentityField(
    #     view_name="blueflow:assetcustomfieldname")

    re_non_alphanum = re.compile(r'[^A-Za-z0-9]+')

    class Meta:  # noqa
        """Wire this serializer to a model."""

        model = AssetCustomFieldName

        # Fields defined in the schema
        tag_fields = tuple(f.name for f in model._meta.fields)

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            'url',
            'num_assets',
            # 'page_url',
        )

        fields = tag_fields + computed_fields

    def validate_display_type(self, display_type_string):
        """Check against the list of display types in the model."""
        valid_display_types = [
            t[0] for t in AssetCustomFieldName.DISPLAY_TYPES]
        if display_type_string not in valid_display_types:
            raise serializers.ValidationError('Invalid display type')
        return display_type_string

    def validate_field_name(self, field_name):
        """Check that a field name doesn't collide with an existing one.

        Checks against:
        - Asset fields (both name and verbose_name)
        - Other AssetCustomFieldName objects
        """
        def normalize(fname):
            """Remove all non-alphanumeric chars and switch to lowercase."""
            return self.re_non_alphanum.sub('', fname.lower())

        other_fields = {normalize(f.name) for f in Asset._meta.fields}
        other_fields |= {normalize(f.verbose_name) for f in Asset._meta.fields}
        other_fields |= {normalize(fname) for fname in
                         AssetCustomFieldName.objects.values_list(
                             'field_name', flat=True)}

        if normalize(field_name) in other_fields:
            raise serializers.ValidationError(
                'Custom field name too similar to existing field name')
        return field_name


class AssetCustomFieldNameViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Custom asset field (name)."""

    waffle_switch = "legacy"

    # AssetCustomFieldName model does have 'objects'
    queryset = AssetCustomFieldName.objects.all()
    serializer_class = AssetCustomFieldNameSerializer
    # filterset_class = AssetCustomFieldNameFilter
    pagination_class = HugeLimitOffsetPagination

    def get_queryset(self):
        """Override so we can order by field_name."""
        qset = super().get_queryset()
        return qset.order_by('field_name')


class AssetCustomFieldSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes custom asset field values.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="api:assetcustomfield-detail")
    # asset = AssetSerializer()
    field = AssetCustomFieldNameSerializer(read_only=True)
    # page_url = serializers.HyperlinkedIdentityField(
    #     view_name="blueflow:assetcustomfield")
    asset_id = IntegerField()
    field_id = IntegerField()

    class Meta:  # noqa
        """Wire this serializer to a model."""

        model = AssetCustomField
        fields = (
            'id',
            'url',
            'asset_id',
            'field',
            'field_id',
            'value_text',
        )


class AssetCustomFieldViewSet(WaffleSwitchMixin, ChangeReasonMixin, viewsets.ModelViewSet):
    """Custom asset field (value)."""

    waffle_switch = "legacy"

    # AssetCustomField model does have 'objects'
    queryset = AssetCustomField.objects.all()
    serializer_class = AssetCustomFieldSerializer
    # filterset_class = AssetCustomFieldFilter
    pagination_class = HugeLimitOffsetPagination
