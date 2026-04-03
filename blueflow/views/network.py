"""ViewSet for networks."""

import logging

import django_filters
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.fields import IntegerField
from rest_framework.response import Response
from waffle.mixins import WaffleSwitchMixin

from blueflow.models import Asset, Cidr, Network, SavedSearch
from blueflow.utils import ipset_from_network

from .utils import HugeLimitOffsetPagination

logger = logging.getLogger(__name__)


class NetworkSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes networks.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="blueflow:network-detail")
    cidr = serializers.JSONField(required=False)

    class Meta:
        model = Network
        # We have to specify these fields since most of them are properties
        # (only name, ok_to_scan, and date_added are real DB fields.)
        fields = (
            "url",
            "id",
            "name",
            "cidr",
            "ok_to_scan",
            "date_added",
            "display_name",
            "type",
            "num_assets",
            "identified_statistics",
        )

    def create(self, validated_data):
        """Override in order to debug-print."""
        logger.debug("Creating: Network validated data is '%s'", validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Override in order to debug-print."""
        logger.debug(
            "Updating: Network validated data is '%s' (instance is '%s')",
            validated_data,
            instance,
        )
        return super().update(instance, validated_data)

    def validate_cidr(self, cidr_string):
        """Take a CIDR or comma-separated list of CIDRs and make it a list."""
        return list(ipset_from_network(cidr_string).iter_cidrs())


class NetworkFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    asset = django_filters.NumberFilter(method="filter_asset")

    @staticmethod
    def filter_asset(queryset, name, value):
        """Get networks that belong to a certain asset."""
        assert name == "asset"
        asset_id = value
        asset = Asset.objects.get(id=asset_id)

        if asset.ip_address is None:
            # objects.none() gives us an empty QuerySet.
            return Network.objects.none()

        network_qset = queryset.filter(cidr__cidr__net_contains=asset.ip_address)
        return network_qset

    class Meta:
        model = Network

        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        # fields = {
        #     'asset': ['exact'],
        #     }
        fields = "__all__"  # Why limit the lookups

        # NOTE: if you want to filter on IP addresses etc., this is
        #   probably possible -- look to
        #   asset.py::AssetFilter.Meta.filter_overrides for inspiration.


class NetworkViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """CIDR-based collection/network of Assets."""

    waffle_switch = "core"

    # Model does have objects...
    queryset = Network.objects.all()
    serializer_class = NetworkSerializer
    filterset_class = NetworkFilter
    pagination_class = HugeLimitOffsetPagination

    @action(detail=False)
    def no_network(self, request):
        """Virtual network, for assets that don't belong to one."""
        asset_qset = Asset.objects.no_network()
        num_assets = asset_qset.count()
        identified_statistics = asset_qset.identified_statistics()
        data = {
            "id": "no_network",
            "name": "Other Assets",
            "cidr": [],
            "num_assets": num_assets,
            "identified_statistics": identified_statistics,
        }
        return Response(data)


class CidrSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes cidrs.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="blueflow:cidr-detail")
    network_id = IntegerField()

    class Meta:
        model = Cidr
        fields = ("id", "url", "cidr", "network_id")


class CidrViewSet(mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    """CIDR-based collection/network of Assets."""

    # Model does have objects...
    queryset = Cidr.objects.all()
    serializer_class = CidrSerializer


class SavedSearchSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes saved searchs.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:savedsearch-detail"
    )

    class Meta:
        model = SavedSearch
        fields = (
            "url",
            "id",
            "name",
            "search_query",
            "ok_to_scan",
            "date_added",
        )
        # We also want to have the URL for the actual search here.  Have
        # to think about how to accomplish this...


class SavedSearchViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """CIDR-based collection/network of Assets."""

    waffle_switch = "core"

    # Model does have objects...
    queryset = SavedSearch.objects.all()
    serializer_class = SavedSearchSerializer
    # NOTE 1: Anyone who's logged in is allowed to save/modify/delete
    #         saved searches (via the API).  (Attn: @ransford.)
    #
    # NOTE 2: The UI has no machinery for editing a saved search... but
    #         it's possible directly via API.
    permission_classes = (permissions.IsAuthenticated,)
