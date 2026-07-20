"""Unit tests for the Viper integration dataclasses (#160).

These tests drive the schema-alignment work: they exercise
``ViperAsset.to_dict()`` and ``ViperWebhookResponse.to_dict()`` directly,
without going through Celery or HTTP, so failures point straight at the
serialization shape.

Wire-level behaviour (what gets POSTed to Viper) is covered separately in
``blueflow/celery/tests/test_viper.py``.
"""

from django.conf import settings
from model_bakery import baker

from blueflow import models
from blueflow.models.viper import ViperAsset, ViperWebhookResponse

DAYS_IN_WEEK = 7
SAMPLE_HOUR_23_COUNT = 5
SAMPLE_TOTAL_COUNT = 42


def _make_asset(**overrides) -> models.Asset:
    defaults = {
        "hostname": "viper-schema-test.example.com",
        "ip_address": "10.0.0.5",
        "mac_address": "00:11:22:33:44:55",
        "model": "Phillips",
    }
    services = None
    if "services" in overrides:
        services = overrides.pop("services")
    defaults.update(overrides)
    ipv4 = defaults.pop("ip_address")
    mac_address = defaults.pop("mac_address")
    asset = baker.make("Asset", **defaults)
    baker.make("NetworkInterface", system=asset, ipv4=ipv4, mac_address=mac_address)
    if services is None:
        return asset
    for s in services:
        asset.add_service(s["port"], s["protocol"])
    return asset


# ---------------------------------------------------------------------------
# ViperAsset
# ---------------------------------------------------------------------------


def test_viper_asset_to_dict_includes_required_keys():
    """Viper's OpenAPI marks ip, upstreamApi, vendorId as required."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    for key in ("ip", "upstreamApi", "vendorId"):
        assert key in payload, f"required key {key!r} missing from payload"


def test_viper_asset_to_dict_drops_blueflow_internal_id():
    """BlueFlow's integer PK is not part of Viper's schema; must not leak."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    assert "id" not in payload


def test_viper_asset_status_literal_is_capitalized_active():
    """Viper's status enum is Active|Decommissioned|Maintenance — capital A."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    assert payload["status"] == "Active"


def test_viper_asset_role_is_populated_from_category():
    """Role maps to asset.category, not a hardcoded blank."""
    asset = _make_asset(category="infusion-pump")
    payload = ViperAsset(asset).to_dict()
    assert payload["role"] == "infusion-pump"


def test_viper_asset_role_omitted_when_category_unset():
    """Role is omitted when no category (Viper rejects empty strings)."""
    asset = _make_asset(category="")
    payload = ViperAsset(asset).to_dict()
    assert "role" not in payload


def test_viper_asset_upstream_api_uses_base_url_and_asset_id():
    """UpstreamApi points back at the asset's BlueFlow detail URL."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    expected = f"{settings.BASE_URL}/api/assets/{asset.id}/"
    assert payload["upstreamApi"] == expected


def test_viper_asset_ip_comes_from_asset_ip_address():
    """Ip is the asset's ip_address as a string."""
    asset = _make_asset(ip_address="192.168.50.10")
    payload = ViperAsset(asset).to_dict()
    assert payload["ip"] == "192.168.50.10"


def test_viper_asset_ip_is_empty_string_when_no_address():
    """Ip falls back to empty string when ip_address is null."""
    asset = _make_asset(ip_address=None)
    payload = ViperAsset(asset).to_dict()
    assert payload["ip"] == ""


def test_viper_asset_location_omitted_when_all_empty():
    """Blank location quadrants are omitted from the wire payload."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    assert "location" not in payload


def test_viper_asset_cpe_matches_expected_for_actual_json_payload():
    """Confirm the CPE produced from the ~/Desktop/actual.json shape.

    The payload uses TapirXL-style names (vendor/product/version); they map to
    the BlueFlow Asset fields manufacturer/model/app_sw_version.
    """
    payload = {
        "hostname": "BRIGHTSPEED01",
        "ip_address": "10.40.2.20",
        "mac_address": "00:10:18:AA:BB:01",
        "vendor": "gehealthcare",
        "product": "brightspeed_elite_select",
        "version": "11.2.0",
        "device_class": "CT",
        "services": [{"port": 5355, "protocol": "TCP"}],
        "confidence": "HIGH",
    }
    asset = _make_asset(
        hostname=payload["hostname"],
        ip_address=payload["ip_address"],
        mac_address=payload["mac_address"],
        manufacturer=payload["vendor"],
        model=payload["product"],
        app_sw_version=payload["version"],
        category=payload["device_class"],
        services=payload["services"],
    )
    expected = f"cpe:2.3:h:{payload['vendor']}:{payload['product']}:-:*:*:*:*:*:*:*"
    assert ViperAsset(asset).cpe == expected


def test_viper_asset_mac_address_is_camel_case():
    asset = _make_asset(mac_address="00:11:22:33:44:55")
    payload = ViperAsset(asset).to_dict()
    assert payload["macAddress"] == "00:11:22:33:44:55"


def test_viper_asset_utilization_is_length_seven_list():
    """Utilization is a 7-element array (Monday=0..Sunday=6)."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    assert isinstance(payload["utilization"], list)
    assert len(payload["utilization"]) == DAYS_IN_WEEK


def test_viper_asset_utilization_with_no_usage_rows_is_seven_empty_dicts():
    """An asset with no Usage rows serialises 7 empty dicts."""
    asset = _make_asset()
    payload = ViperAsset(asset).to_dict()
    assert payload["utilization"] == [{}, {}, {}, {}, {}, {}, {}]


def test_viper_asset_utilization_excludes_zero_count_hours():
    """Hours with count==0 are omitted from each day's dict."""
    asset = _make_asset()
    models.Usage.objects.create(
        asset=asset,
        day_of_week=models.DayOfWeek.WEDNESDAY,
        hour_09=3,
        hour_10=0,
        hour_14=2,
    )
    payload = ViperAsset(asset).to_dict()
    wednesday = payload["utilization"][models.DayOfWeek.WEDNESDAY]
    assert wednesday == {"9": 3, "14": 2}


def test_viper_asset_utilization_uses_string_hour_keys():
    """Hour keys are stringified ints (JSON requires string keys anyway)."""
    asset = _make_asset()
    models.Usage.objects.create(
        asset=asset,
        day_of_week=models.DayOfWeek.MONDAY,
        hour_00=1,
        hour_23=SAMPLE_HOUR_23_COUNT,
    )
    payload = ViperAsset(asset).to_dict()
    monday = payload["utilization"][models.DayOfWeek.MONDAY]
    assert "0" in monday
    assert "23" in monday
    assert monday["0"] == 1
    assert monday["23"] == SAMPLE_HOUR_23_COUNT


# ---------------------------------------------------------------------------
# ViperWebhookResponse
# ---------------------------------------------------------------------------


def _make_response(**overrides) -> ViperWebhookResponse:
    defaults = {
        "items": [],
        "page": 1,
        "page_size": 10,
        "total_count": 0,
        "total_pages": 1,
        "since": "2026-01-01T00:00:00Z",
        "before": None,
        "request_id": "req-abc",
    }
    defaults.update(overrides)
    return ViperWebhookResponse(**defaults)


def test_response_uses_total_count_key_not_total():
    """Wrapper emits totalCount (camelCase) for Viper integrationUpload."""
    response = _make_response(total_count=SAMPLE_TOTAL_COUNT)
    payload = response.to_dict()
    assert "totalCount" in payload
    assert payload["totalCount"] == SAMPLE_TOTAL_COUNT
    assert "total" not in payload
    assert "total_count" not in payload


def test_response_uses_next_and_previous_keys_not_page_suffixed():
    """Wrapper renames: next_page → next, previous_page → previous."""
    response = _make_response(page=2, total_count=30, total_pages=3)
    payload = response.to_dict()
    assert "next" in payload
    assert "previous" in payload
    assert "next_page" not in payload
    assert "previous_page" not in payload


def test_response_first_page_has_null_previous():
    """Previous is None on page 1."""
    response = _make_response(page=1, total_count=30, total_pages=3)
    payload = response.to_dict()
    assert payload["previous"] is None


def test_response_last_page_has_null_next():
    """Next is None on the final page."""
    response = _make_response(page=3, total_count=30, total_pages=3)
    payload = response.to_dict()
    assert payload["next"] is None


def test_response_drops_internal_only_fields():
    """since, before, request_id, webhook_path are internal — not on the wire."""
    response = _make_response(
        since="2026-01-01T00:00:00Z",
        before="2026-01-02T00:00:00Z",
        request_id="req-xyz",
    )
    payload = response.to_dict()
    for key in ("since", "before", "request_id", "webhook_path"):
        assert key not in payload, f"internal field {key!r} leaked to the wire"


def test_response_emits_items_key_not_assets():
    """The list key is items, not assets."""
    response = _make_response()
    payload = response.to_dict()
    assert "items" in payload
    assert "assets" not in payload


def test_response_serializes_items_via_viper_asset_to_dict():
    """Items in the wrapper are ViperAsset.to_dict() outputs, not dataclass dumps."""
    asset = _make_asset()
    response = _make_response(items=[ViperAsset(asset)], total_count=1)
    payload = response.to_dict()
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert "ip" in item
    assert "id" not in item
