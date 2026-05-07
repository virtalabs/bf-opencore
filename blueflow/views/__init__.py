"""API Views."""

# ViewSets
from .alert import AlertSerializer, AlertViewSet
from .asset import AssetSerializer, AssetViewSet, HistoricalAssetSerializer
from .assetgroup import AssetGroupSerializer, AssetGroupViewSet
from .assettag import AssetTagSerializer, AssetTagViewSet
from .assetvulnerability import AssetVulnerabilitySerializer, AssetVulnerabilityViewSet
from .autocomplete import AutocompleteAssetFieldViewSet
from .group import GroupSerializer, GroupViewSet
from .network import CidrViewSet, NetworkSerializer, NetworkViewSet, SavedSearchViewSet
from .periodic_task import (
    CrontabScheduleSerializer,
    CrontabScheduleViewSet,
    IntervalScheduleSerializer,
    IntervalScheduleViewSet,
    PeriodicTaskSerializer,
    PeriodicTaskViewSet,
)
from .scan import ScanSerializer, ScanViewSet
from .tag import TagSerializer, TagViewSet
from .user import UserSerializer, UserViewSet
from .viper import ViperViewSet
from .vulnerability import VulnerabilitySerializer, VulnerabilityViewSet

__all__ = [
    "AlertSerializer",
    "AlertViewSet",
    "AssetGroupSerializer",
    "AssetGroupViewSet",
    "AssetSerializer",
    "AssetTagSerializer",
    "AssetTagViewSet",
    "AssetViewSet",
    "AssetVulnerabilitySerializer",
    "AssetVulnerabilityViewSet",
    "AutocompleteAssetFieldViewSet",
    "CidrViewSet",
    "CrontabScheduleSerializer",
    "CrontabScheduleViewSet",
    "GroupSerializer",
    "GroupViewSet",
    "HistoricalAssetSerializer",
    "IntervalScheduleSerializer",
    "IntervalScheduleViewSet",
    "NetworkSerializer",
    "NetworkViewSet",
    "PeriodicTaskSerializer",
    "PeriodicTaskViewSet",
    "SavedSearchViewSet",
    "ScanSerializer",
    "ScanViewSet",
    "TagSerializer",
    "TagViewSet",
    "UserSerializer",
    "UserViewSet",
    "ViperViewSet",
    "VulnerabilitySerializer",
    "VulnerabilityViewSet",
]
