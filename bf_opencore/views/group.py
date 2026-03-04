"""ViewSet for groups."""

import logging

import django_filters
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import IntegrityError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import Asset, AssetGroup, Group
from bf_opencore.utils import iterable

from .utils import HugeLimitOffsetPagination

logger = logging.getLogger(__name__)


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes groups.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="bf_opencore:group-detail")
    add_assets_url = serializers.HyperlinkedIdentityField(
        view_name="bf_opencore:group-assets"
    )
    # assets = serializers.HyperlinkedRelatedField(
    #     many=True,
    #     read_only=True,
    #     view_name='bf_opencore:asset-detail'
    # )

    class Meta:
        """Wire this serializer to a model."""

        model = Group

        # Fields defined in the schema
        group_fields = tuple(f.name for f in model._meta.fields)

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            "url",
            "add_assets_url",
            "num_assets",
            "identified_statistics",
        )

        fields = group_fields + computed_fields


class GroupFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:  # noqa
        model = Group

        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields = {
            "asset": ["exact"],
        }


class GroupViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Free-text group associated with one or more assets."""

    waffle_switch = "core"

    # Group model does have 'objects'
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    filterset_class = GroupFilter
    pagination_class = HugeLimitOffsetPagination

    @action(detail=True, methods=["POST"])
    def assets(self, request, pk):
        """Add several assets to this Group."""
        group = self.get_object()

        # Add several new assets to this group with a POST
        # request to /api/groups/<n>/assets/.
        # The POST data must contain a list of asset IDs.
        asset_ids = request.data.get("asset_ids")
        logger.debug("Got asset IDs '%s' of type '%s'", asset_ids, type(asset_ids))

        if asset_ids is None:
            raise serializers.ValidationError(
                {"asset_ids": ["'asset_ids' is required"]}
            )
        if not iterable(asset_ids):
            raise serializers.ValidationError(
                {"asset_ids": ["'asset_ids' must be a list"]}
            )

        assets_existing = assets_new = 0
        for asset_id in asset_ids:
            try:
                asset = Asset.objects.get(pk=asset_id)
            except (ObjectDoesNotExist, ValueError):
                raise serializers.ValidationError(
                    {
                        "asset_ids": [f"Asset does not exist: id={asset_id}"],
                    }
                )
            asset_group = AssetGroup(
                asset=asset, group=group, provenance="Bulk Add via API"
            )
            try:
                asset_group.save()
                logger.debug(
                    "Created new asset-group link between %s and %s: %s",
                    asset,
                    group,
                    asset_group,
                )
                assets_new += 1
            except IntegrityError:
                asset_group = AssetGroup.objects.get(asset=asset, group=group)
                logger.debug(
                    "Asset-group link between %s and %s already existed: %s",
                    asset,
                    group,
                    asset_group,
                )
                assets_existing += 1

        return Response(
            {"# New assets added": assets_new, "# Existing assets": assets_existing},
            status=(status.HTTP_201_CREATED if assets_new else status.HTTP_200_OK),
        )
