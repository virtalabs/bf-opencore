"""Blueflow Django app URLs."""

app_name = "blueflow"

from django.conf.urls import include
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken import views as authview
from rest_framework.routers import DefaultRouter

from . import views

API_TITLE = "BlueFlow REST API"

router = DefaultRouter()
# Regular BlueFlow Models
router.register(r"alerts", views.AlertViewSet)
router.register(r"assets", views.AssetViewSet)
router.register(r"assetcustomfieldnames", views.AssetCustomFieldNameViewSet)
router.register(r"assetcustomfields", views.AssetCustomFieldViewSet)
router.register(r"assetgroups", views.AssetGroupViewSet)
router.register(r"assettags", views.AssetTagViewSet)
router.register(r"assetvulnerabilities", views.AssetVulnerabilityViewSet)
router.register(r"attachments", views.AttachmentViewSet)
router.register(
    r"autocomplete_field",
    views.AutocompleteAssetFieldViewSet,
    basename="autocomplete_field",
)
router.register(r"cidrs", views.CidrViewSet)
router.register(r"groups", views.GroupViewSet)
router.register(r"networks", views.NetworkViewSet)
router.register(r"network_endpoints", views.NetworkEndpointViewSet)
router.register(r"pulse", views.PulseFeedItemViewSet)
router.register(r"tags", views.TagViewSet)
router.register(r"savedsearches", views.SavedSearchViewSet)
router.register(r"scans", views.ScanViewSet)
router.register(r"users", views.UserViewSet)
router.register(r"vulnerabilities", views.VulnerabilityViewSet)
# Synthetic Models
router.register(r"autocomplete", views.AutocompleteViewSet, basename="autocomplete")
# Celery Beat (periodic tasks) models
router.register(r"crontabs", views.CrontabScheduleViewSet)
router.register(r"intervals", views.IntervalScheduleViewSet)
router.register(r"periodictask", views.PeriodicTaskViewSet)

# Viper integration
router.register(r"viper", views.ViperViewSet, basename="viper")


urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="blueflow:schema"),
        name="swagger-ui",
    ),
    path(r"api-token-auth/", authview.obtain_auth_token, name="auth-token"),
    path("", include(router.urls)),
]
