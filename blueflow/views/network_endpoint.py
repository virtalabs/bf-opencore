"""API View for NetflowRecord."""

from rest_framework import serializers, viewsets
from waffle.mixins import WaffleSwitchMixin

from blueflow.models import Asset, EndpointSuggestion, NetworkEndpoint

from .asset import AssetSerializer
from .utils import PaginateRelationsMixin


class EndpointSuggestionSerializer(serializers.ModelSerializer):
    """Serialize an EndpointSuggestion."""

    asset = AssetSerializer()

    class Meta:
        """Wire this serializer to a model."""

        model = EndpointSuggestion
        fields = tuple(f.name for f in model._meta.fields)


class NetworkEndpointSerializer(serializers.HyperlinkedModelSerializer):
    """Serialize a NetworkEndpoint."""

    asset = AssetSerializer(read_only=True)
    asset_id = serializers.IntegerField(default=None, source="asset.id")
    suggestions = EndpointSuggestionSerializer(many=True)
    blacklist = serializers.ListField(child=serializers.IntegerField(min_value=0))

    class Meta:
        """Wire this serializer to a model."""

        model = NetworkEndpoint
        fields = tuple(
            f.name for f in model._meta.fields if not f.name.startswith("_")
        ) + ("asset_id", "asset", "suggestions", "blacklist")

    def validate_asset_id(self, value):
        """Check asset ID is valid."""
        try:
            value = int(value)
            Asset.objects.get(id=value)
            return value
        except ValueError:
            raise serializers.ValidationError("Must be an integer")
        except Asset.DoesNotExist:
            raise serializers.ValidationError("No Asset with that ID")

    def create(self, validated_data):
        """Create a NetworkEndpoint, assigning Asset by asset_id."""
        definite_asset = validated_data.pop("asset", None)
        asset = None
        if definite_asset:
            asset = Asset.objects.get(id=definite_asset["id"])
        return NetworkEndpoint.objects.create(asset=asset, **validated_data)

    def update(self, instance, validated_data):
        """Update a NetworkEndpoint, assigning Asset by asset_id."""
        definite_asset = validated_data.pop("asset", None)
        super().update(instance, validated_data)
        if definite_asset:
            asset = Asset.objects.get(id=definite_asset["id"])
            instance.asset = asset
            instance.save()
        return instance


class NetworkEndpointViewSet(
    WaffleSwitchMixin, PaginateRelationsMixin, viewsets.ModelViewSet
):
    """Viewset for Network Endpoints."""

    waffle_switch = "core"

    queryset = NetworkEndpoint.objects.order_by("-max_confidence")
    serializer_class = NetworkEndpointSerializer
