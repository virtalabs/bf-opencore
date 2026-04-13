"""Tapirx upsert contract tests.

Validates that Tapirx can PUT to /api/assets/upsert/ to create or update
assets by MAC address, and that assets are retrievable via GET
/api/assets/{id}/.
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from blueflow import models

# Full Tapirx payload per asset.go - used for contract tests
TAPIRX_FULL_PAYLOAD = {
    "ip_address": "10.0.0.155",
    "open_ports_tcp": [2575],
    "mac_address": "00:03:b1:b5:b6:48",
    "name": "Infuse-O-Matic Peach B+",
    "provenance": "HL7 PRT-16",
    "last_seen": "2019-01-02T12:37:22.938687-08:00",
    "client_id": "mymachine.example.com",
}


def _put_upsert(client: APIClient, payload: dict) -> object:
    """PUT payload to upsert endpoint."""
    return client.put(
        "/api/assets/upsert/",
        json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Section 1: Contract tests
# ---------------------------------------------------------------------------


def test_tapirx_upsert_create(asset_edit_client: APIClient) -> None:
    """PUT full Tapirx payload, assert 201, verify ip_address, name, open_ports_tcp."""
    response = _put_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["ip_address"] == "10.0.0.155"
    assert response.data["name"] == "Infuse-O-Matic Peach B+"
    assert response.data["open_ports_tcp"] == [2575]
    assert models.Asset.objects.count() == 1


def test_tapirx_upsert_update(asset_edit_client: APIClient) -> None:
    """PUT twice same MAC, assert 200 on second, verify field update."""
    payload1 = {
        "mac_address": "11:22:33:44:55:66",
        "ip_address": "10.0.0.1",
        "name": "Original Name",
    }
    response1 = _put_upsert(asset_edit_client, payload1)
    assert response1.status_code == status.HTTP_201_CREATED

    payload2 = {
        "mac_address": "11:22:33:44:55:66",
        "ip_address": "10.0.0.2",
        "name": "Updated Name",
    }
    response2 = _put_upsert(asset_edit_client, payload2)
    assert response2.status_code == status.HTTP_200_OK
    assert response2.data["ip_address"] == "10.0.0.2"
    assert response2.data["name"] == "Updated Name"
    assert models.Asset.objects.count() == 1


def test_tapirx_upsert_minimal(asset_edit_client: APIClient) -> None:
    """PUT only mac_address, assert 201."""
    response = _put_upsert(asset_edit_client, {"mac_address": "00:03:b1:b5:b6:48"})
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["mac_address"] == "00:03:b1:b5:b6:48"
    assert models.Asset.objects.count() == 1


def test_tapirx_upsert_no_mac_400(asset_edit_client: APIClient) -> None:
    """PUT without mac_address, assert 400."""
    response = _put_upsert(
        asset_edit_client,
        {"ip_address": "10.0.0.1", "name": "No MAC"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 0


def test_tapirx_upsert_token_auth(tapirx_token_client: APIClient) -> None:
    """PUT with tapirx_token_client (Token header), assert 201."""
    response = _put_upsert(tapirx_token_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["mac_address"] == "00:03:b1:b5:b6:48"
    assert models.Asset.objects.count() == 1


@pytest.mark.skip(reason="Blueflow uses AllowAny; auth enforced by consuming product")
def test_tapirx_upsert_unauth_403(db: None, enable_core_switch: None) -> None:  # noqa: ARG001
    """PUT unauthenticated would assert 403 if IsAuthenticated were enforced."""
    client = APIClient()
    response = client.put(
        "/api/assets/upsert/",
        json.dumps(TAPIRX_FULL_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert models.Asset.objects.count() == 0


def test_tapirx_upsert_ignored_fields(asset_edit_client: APIClient) -> None:
    """connect_port_tcp and ipv6_address are silently dropped."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "ipv6_address": "::1",
        "connect_port_tcp": "9999",
    }
    response = _put_upsert(asset_edit_client, payload)
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get()
    assert asset.mac_address == "11:22:33:44:55:66"
    assert not hasattr(asset, "ipv6_address") or asset.ipv6_address is None
    assert not hasattr(asset, "connect_port_tcp")


def test_tapirx_upsert_open_ports_merge(asset_edit_client: APIClient) -> None:
    """PUT with open_ports_tcp merges with existing ports."""
    payload1 = {
        "mac_address": "11:22:33:44:55:66",
        "open_ports_tcp": [80, 443],
    }
    response1 = _put_upsert(asset_edit_client, payload1)
    assert response1.status_code == status.HTTP_201_CREATED
    assert set(response1.data["open_ports_tcp"]) == {80, 443}

    # Second PUT adds new ports, keeps existing
    payload2 = {
        "mac_address": "11:22:33:44:55:66",
        "open_ports_tcp": [443, 8080],
    }
    response2 = _put_upsert(asset_edit_client, payload2)
    assert response2.status_code == status.HTTP_200_OK
    assert set(response2.data["open_ports_tcp"]) == {80, 443, 8080}


# ---------------------------------------------------------------------------
# Section 2: GET round-trip
# ---------------------------------------------------------------------------


def test_get_asset_by_id_after_upsert(asset_edit_client: APIClient) -> None:
    """PUT upsert, extract id, GET /api/assets/{id}/, assert 200 and fields match."""
    response = _put_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    asset_id = response.data["id"]
    get_response = asset_edit_client.get(f"/api/assets/{asset_id}/")
    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.data["id"] == asset_id
    assert get_response.data["ip_address"] == "10.0.0.155"
    assert get_response.data["name"] == "Infuse-O-Matic Peach B+"
    assert get_response.data["mac_address"] == "00:03:b1:b5:b6:48"


def test_get_asset_after_upsert_404(asset_edit_client: APIClient) -> None:
    """GET /api/assets/99999/, assert 404."""
    response = asset_edit_client.get("/api/assets/99999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.skip(reason="Blueflow uses AllowAny; auth enforced by consuming product")
def test_get_asset_after_upsert_unauth_403(db: None, enable_core_switch: None) -> None:  # noqa: ARG001
    """GET without auth would assert 403 if IsAuthenticated were enforced."""
    asset = models.Asset.objects.create(mac_address="aa:bb:cc:dd:ee:ff")
    client = APIClient()
    response = client.get(f"/api/assets/{asset.id}/")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Section 3: Functional
# ---------------------------------------------------------------------------


def test_upsert_then_list(asset_edit_client: APIClient) -> None:
    """PUT upsert, GET /api/assets/, assert count=1 and asset in results."""
    response = _put_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    list_response = asset_edit_client.get("/api/assets/")
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["count"] == 1
    results = list_response.data["results"]
    assert len(results) == 1
    assert results[0]["mac_address"] == "00:03:b1:b5:b6:48"


@pytest.mark.skip(
    reason="django-simple-history update_change_reason filter fails with netfields"
)
def test_upsert_history_reason(asset_edit_client: APIClient) -> None:
    """PUT upsert with provenance/client_id/last_seen, assert history_change_reason."""
    response = _put_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get()
    latest = asset.history.order_by("-history_date").first()
    assert latest is not None
    reason = latest.history_change_reason
    assert reason is not None
    assert "HL7 PRT-16" in reason
    assert "mymachine.example.com" in reason
    assert "2019-01-02" in reason


def test_upsert_nic_vendor_from_mac(asset_edit_client: APIClient) -> None:
    """PUT with registered OUI MAC, assert nic_vendor auto-populated from netaddr."""
    response = _put_upsert(
        asset_edit_client,
        {"mac_address": "00:03:b1:b5:b6:48", "name": "Medical device"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    # OUI 00:03:b1 is registered; vendor may be Hospira, ICU Medical, etc.
    assert response.data["nic_vendor"] is not None
    assert len(response.data["nic_vendor"]) > 0
    asset = models.Asset.objects.get()
    assert asset.nic_vendor is not None


# ---------------------------------------------------------------------------
# Section 4: PUT semantics and deprecation
# ---------------------------------------------------------------------------


def test_upsert_put_idempotency(asset_edit_client: APIClient) -> None:
    """PUT same payload 3 times, assert only 1 asset exists."""
    payload = {"mac_address": "11:22:33:44:55:66", "ip_address": "10.0.0.1"}
    response1 = _put_upsert(asset_edit_client, payload)
    assert response1.status_code == status.HTTP_201_CREATED

    response2 = _put_upsert(asset_edit_client, payload)
    assert response2.status_code == status.HTTP_200_OK

    response3 = _put_upsert(asset_edit_client, payload)
    assert response3.status_code == status.HTTP_200_OK

    assert models.Asset.objects.count() == 1


def test_upsert_legacy_field_names_ignored(
    asset_edit_client: APIClient,
) -> None:
    """PUT with legacy field names — they are ignored, not coerced."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "ipv4_address": "10.0.0.1",
        "identifier": "Legacy Device",
    }
    response = _put_upsert(asset_edit_client, payload)
    # Legacy fields are unknown to the serializer and silently dropped.
    # The asset is created with only mac_address.
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["ip_address"] is None
    assert response.data["name"] is None


def test_upsert_modern_field_names(asset_edit_client: APIClient) -> None:
    """PUT with canonical field names (ip_address, name) works directly."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "ip_address": "10.0.0.1",
        "name": "Modern Device",
    }
    response = _put_upsert(asset_edit_client, payload)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["ip_address"] == "10.0.0.1"
    assert response.data["name"] == "Modern Device"


def test_upsert_no_deprecation_header(asset_edit_client: APIClient) -> None:
    """PUT response does not include Deprecation header."""
    response = _put_upsert(
        asset_edit_client, {"mac_address": "11:22:33:44:55:66"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert "Deprecation" not in response
    assert "Link" not in response


def test_upsert_post_method_not_allowed(asset_edit_client: APIClient) -> None:
    """POST to upsert endpoint returns 405 Method Not Allowed."""
    response = asset_edit_client.post(
        "/api/assets/upsert/",
        json.dumps({"mac_address": "11:22:33:44:55:66"}),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_upsert_empty_mac_400(asset_edit_client: APIClient) -> None:
    """PUT with empty string mac_address returns 400."""
    response = _put_upsert(asset_edit_client, {"mac_address": ""})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 0


def test_upsert_null_mac_400(asset_edit_client: APIClient) -> None:
    """PUT with null mac_address returns 400."""
    response = _put_upsert(asset_edit_client, {"mac_address": None})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 0


def test_upsert_invalid_port_400(asset_edit_client: APIClient) -> None:
    """PUT with out-of-range port in open_ports_tcp returns 400."""
    response = _put_upsert(
        asset_edit_client,
        {"mac_address": "11:22:33:44:55:66", "open_ports_tcp": [70000]},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_upsert_non_numeric_port_400(asset_edit_client: APIClient) -> None:
    """PUT with non-integer in open_ports_tcp returns 400."""
    response = _put_upsert(
        asset_edit_client,
        {"mac_address": "11:22:33:44:55:66", "open_ports_tcp": ["abc"]},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_upsert_open_ports_normalized(asset_edit_client: APIClient) -> None:
    """PUT with duplicate/unsorted ports stores them deduplicated and sorted."""
    response = _put_upsert(
        asset_edit_client,
        {"mac_address": "11:22:33:44:55:66", "open_ports_tcp": [443, 80, 443, 8080, 80]},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["open_ports_tcp"] == [80, 443, 8080]
