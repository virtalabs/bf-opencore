"""Blueflow Django app URLs."""

from django.conf.urls import include
from django.urls import path
from drf_spectacular.views import SpectacularAPIView
from rest_framework.authtoken import views as authview
from rest_framework.routers import DefaultRouter

from . import views
from .scalar_viewer import scalar_viewer

app_name = "blueflow"

router = DefaultRouter()
# Regular BlueFlow Models
router.register(r"assets", views.AssetViewSet)
router.register(r"assetgroups", views.AssetGroupViewSet)
router.register(r"assettags", views.AssetTagViewSet)
router.register(r"cidrs", views.CidrViewSet)
router.register(r"groups", views.GroupViewSet)
router.register(r"tags", views.TagViewSet)
router.register(r"savedsearches", views.SavedSearchViewSet)
router.register(r"scans", views.ScanViewSet)
router.register(r"users", views.UserViewSet)

# Celery Beat (periodic tasks) models
router.register(r"crontabs", views.CrontabScheduleViewSet)
router.register(r"intervals", views.IntervalScheduleViewSet)
router.register(r"periodictask", views.PeriodicTaskViewSet)

# Viper integration
router.register(r"viper", views.ViperViewSet, basename="viper")


urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", scalar_viewer, name="api-docs"),
    path(r"api-token-auth/", authview.obtain_auth_token, name="auth-token"),
    path("", include(router.urls)),
]
