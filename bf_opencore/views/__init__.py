"""API Views."""

# ViewSets
from .alert import AlertSerializer, AlertViewSet
from .asset import AssetSerializer, AssetViewSet, HistoricalAssetSerializer
from .asset_custom_field import AssetCustomFieldNameViewSet, AssetCustomFieldViewSet
from .assetgroup import AssetGroupSerializer, AssetGroupViewSet
from .assettag import AssetTagSerializer, AssetTagViewSet
from .assetvulnerability import AssetVulnerabilitySerializer, AssetVulnerabilityViewSet
from .attachment import AttachmentSerializer, AttachmentViewSet
from .autocomplete import (
    AutocompleteAssetFieldViewSet,
    AutocompleteSerializer,
    AutocompleteViewSet,
)
from .group import GroupSerializer, GroupViewSet
from .network import CidrViewSet, NetworkSerializer, NetworkViewSet, SavedSearchViewSet
from .network_endpoint import (
    EndpointSuggestionSerializer,
    NetworkEndpointSerializer,
    NetworkEndpointViewSet,
)
from .periodic_task import (
    CrontabScheduleSerializer,
    CrontabScheduleViewSet,
    IntervalScheduleSerializer,
    IntervalScheduleViewSet,
    PeriodicTaskSerializer,
    PeriodicTaskViewSet,
)
from .pulse import PulseFeedItemSerializer, PulseFeedItemViewSet
from .scan import ScanSerializer, ScanViewSet
from .tag import TagSerializer, TagViewSet
from .user import UserSerializer, UserViewSet
from .viper import ViperViewSet
from .vulnerability import VulnerabilitySerializer, VulnerabilityViewSet

__all__ = [
    # ViewSets
    "AlertViewSet",
    "AssetViewSet",
    "AssetCustomFieldNameViewSet",
    "AssetCustomFieldViewSet",
    "AssetGroupViewSet",
    "AssetTagViewSet",
    "AssetVulnerabilityViewSet",
    "AttachmentViewSet",
    "AutocompleteViewSet",
    "AutocompleteAssetFieldViewSet",
    "CidrViewSet",
    "ConnectorViewSet",
    "ConnectorTaskViewSet",
    "CrontabScheduleViewSet",
    "GroupViewSet",
    "IntervalScheduleViewSet",
    "NetworkViewSet",
    "NetworkEndpointViewSet",
    "PeriodicTaskViewSet",
    "PulseFeedItemViewSet",
    "SavedSearchViewSet",
    "ScanViewSet",
    "TagViewSet",
    "UserViewSet",
    "VulnerabilityViewSet",
    # Serializers
    "AlertSerializer",
    "AssetSerializer",
    "AssetGroupSerializer",
    "AssetTagSerializer",
    "AssetVulnerabilitySerializer",
    "AttachmentSerializer",
    "AutocompleteSerializer",
    "ConnectorSerializer",
    "ConnectorTaskSerializer",
    "CrontabScheduleSerializer",
    "EndpointSuggestionSerializer",
    "GroupSerializer",
    "HistoricalAssetSerializer",
    "IntervalScheduleSerializer",
    "NetworkEndpointSerializer",
    "NetworkSerializer",
    "PeriodicTaskSerializer",
    "PulseFeedItemSerializer",
    "ScanSerializer",
    "TagSerializer",
    "UserSerializer",
    "VulnerabilitySerializer",
    "ViperViewSet",
]
