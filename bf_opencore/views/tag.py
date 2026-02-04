"""ViewSet for tags."""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import IntegrityError

import django_filters
from rest_framework import viewsets, serializers, status
from rest_framework.response import Response
from rest_framework.decorators import action
from simple_history import utils as hist_utils
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import Tag, Asset, AssetTag

from utils import iterable
from .utils import HugeLimitOffsetPagination
from .utils import ChangeReasonMixin

logger = logging.getLogger(__name__)


class TagSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes tags.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    # Since we namespace with `api:` we have to specify the view-name.
    # This is a little strange...
    url = serializers.HyperlinkedIdentityField(view_name="api:tag-detail")
    page_url = serializers.HyperlinkedIdentityField(view_name="blueflow:tag")
    add_assets_url = serializers.HyperlinkedIdentityField(
        view_name="api:tag-assets")

    class Meta:  # noqa
        """Wire this serializer to a model."""

        model = Tag

        # Fields defined in the schema
        tag_fields = tuple(f.name for f in model._meta.fields)

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            'url',
            'page_url',
            'add_assets_url',
            'num_assets',
        )

        fields = tag_fields + computed_fields

    def validate_color(self, color):
        """Ensure that incoming color is on the format '#aabbcc'.

        - No more than '#' + 6 characters
        - Prepend '#' if necessary
        - Ensure '#' prefix
        - Ensure valid hex
        """
        # logger.debug("Validating color '%s'", color)
        if len(color) < 7 and color[0] != '#':
            color = '#' + color
        if not color[0] == '#':
            raise serializers.ValidationError("{} is not a valid color, must "
                                              "start with '#'".format(color))
        try:
            dummy_int = int(color[1:], 16)
        except ValueError:
            raise serializers.ValidationError("{} is not a valid RGB color"
                                              "".format(color))
        return color


class TagFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:  # noqa
        model = Tag

        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields = {
            'asset': ['exact'],
            }


class TagViewSet(WaffleSwitchMixin, ChangeReasonMixin, viewsets.ModelViewSet):
    """Free-text tag associated with one or more assets."""

    waffle_switch = "legacy"

    # Tag model does have 'objects'
    queryset = Tag.objects.order_by('name')
    serializer_class = TagSerializer
    filterset_class = TagFilter
    pagination_class = HugeLimitOffsetPagination

    @action(detail=True, methods=['POST'])
    def assets(self, request, pk):
        """Add several assets to this Tag."""
        tag = self.get_object()

        # Add several new assets to this tag with a POST
        # request to /api/tags/<n>/assets/.
        # The POST data must contain a list of asset IDs.
        asset_ids = request.data.get('asset_ids')
        logger.debug("Got asset IDs '%s' of type '%s'",
                     asset_ids, type(asset_ids))

        if asset_ids is None:
            raise serializers.ValidationError({
                'asset_ids': ["'asset_ids' is required"]})
        if not iterable(asset_ids):
            raise serializers.ValidationError({
                'asset_ids': ["'asset_ids' must be a list"]})

        assets_existing = assets_new = 0
        for asset_id in asset_ids:
            try:
                asset = Asset.objects.get(pk=asset_id)
            except (ObjectDoesNotExist, ValueError):
                raise serializers.ValidationError({
                    'asset_ids': ["Asset does not exist: id={}"
                                  "".format(asset_id)]
                    })
            reason = 'Bulk Add via API'
            asset_tag = AssetTag(asset=asset, tag=tag,
                                 provenance=reason)
            try:
                asset_tag.save()
                # The ChangeReasonMixin won't work here, so we do it manually
                hist_utils.update_change_reason(asset_tag, reason)
                logger.debug("Created new asset-tag link between "
                             "%s and %s: %s", asset, tag, asset_tag)
                assets_new += 1
            except IntegrityError:
                asset_tag = AssetTag.objects.get(asset=asset, tag=tag)
                logger.debug("Asset-tag link between %s and %s already "
                             "existed: %s", asset, tag, asset_tag)
                assets_existing += 1

        return Response({"# New assets added": assets_new,
                         "# Existing assets": assets_existing},
                        status=(status.HTTP_201_CREATED
                                if assets_new
                                else status.HTTP_200_OK))
