"""API Views."""

from blueflow.serializers import AssetRequestSerializer

from .asset import AssetViewSet
from .assetgroup import AssetGroupSerializer, AssetGroupViewSet
from .assettag import AssetTagSerializer, AssetTagViewSet
from .group import GroupSerializer, GroupViewSet
from .periodic_task import (
    CrontabScheduleSerializer,
    CrontabScheduleViewSet,
    IntervalScheduleSerializer,
    IntervalScheduleViewSet,
    PeriodicTaskSerializer,
    PeriodicTaskViewSet,
)
from .tag import TagSerializer, TagViewSet
from .user import UserSerializer, UserViewSet
from .viper import ViperViewSet

__all__ = [
    "AssetGroupSerializer",
    "AssetGroupViewSet",
    "AssetRequestSerializer",
    "AssetTagSerializer",
    "AssetTagViewSet",
    "AssetViewSet",
    "CrontabScheduleSerializer",
    "CrontabScheduleViewSet",
    "GroupSerializer",
    "GroupViewSet",
    "IntervalScheduleSerializer",
    "IntervalScheduleViewSet",
    "PeriodicTaskSerializer",
    "PeriodicTaskViewSet",
    "TagSerializer",
    "TagViewSet",
    "UserSerializer",
    "UserViewSet",
    "ViperViewSet",
]
