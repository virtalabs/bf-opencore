"""Upsert endpoint contract tests.

Validates that passive scanners can PUT to /api/assets/upsert/ to create
or update assets by MAC address, and that assets are retrievable via
GET /api/assets/{id}/.
"""

import json

import netaddr
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from blueflow import models

# Full scanner payload — used for contract tests
SCANNER_FULL_PAYLOAD = {
    "ip_address": "10.0.0.155",
    "services": [{"port": 2575, "protocol": "tcp"}],
    "mac_address": "00:03:b1:b5:b6:48",
    "manufacturer": "Hospira",
    "name": "Infuse-O-Matic Peach B+",
    "provenance": "HL7 PRT-16",
    "last_seen": "2019-01-02T12:37:22.938687-08:00",
    "client_id": "mymachine.example.com",
}


def _service_pairs(asset: "models.Asset") -> set[tuple[int, str]]:
    """``{(port, protocol), ...}`` for an asset's through-table rows."""
    return set(
        asset.port_protocols.values_list(
            "port_protocol__port", "port_protocol__protocol"
        )
    )


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


def test_upsert_create_full_payload(asset_edit_client: APIClient) -> None:
    """PUT full scanner payload, assert 201, verify ip_address, name, services."""
    response = _put_upsert(asset_edit_client, SCANNER_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["interface"]["ipv4"] == "10.0.0.155"
    assert response.data["name"] == "Infuse-O-Matic Peach B+"
    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert _service_pairs(asset) == {(2575, "tcp")}


def test_upsert_update_by_mac(asset_edit_client: APIClient) -> None:
    """PUT twice same MAC, assert 200 on second, verify field update."""
    payload1 = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "ip_address": "10.0.0.1",
        "name": "Original Name",
    }
    response1 = _put_upsert(asset_edit_client, payload1)
    assert response1.status_code == status.HTTP_201_CREATED

    payload2 = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "ip_address": "10.0.0.2",
        "name": "Updated Name",
    }
    response2 = _put_upsert(asset_edit_client, payload2)
    assert response2.status_code == status.HTTP_200_OK
    assert response2.data["interface"]["ipv4"] == "10.0.0.2"
    assert response2.data["name"] == "Updated Name"
    assert models.Asset.objects.count() == 1


def test_upsert_minimal(asset_edit_client: APIClient) -> None:
    """PUT mac_address + manufacturer (the required minimum), assert 201."""
    response = _put_upsert(
        asset_edit_client,
        {"mac_address": "00:03:b1:b5:b6:48", "manufacturer": "Acme"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert netaddr.EUI(response.data["interface"]["mac_address"]) == netaddr.EUI(
        "00:03:b1:b5:b6:48"
    )
    assert models.Asset.objects.count() == 1


def test_upsert_missing_mac_400(asset_edit_client: APIClient) -> None:
    """PUT without mac_address, assert 400."""
    response = _put_upsert(
        asset_edit_client,
        {"ip_address": "10.0.0.1", "name": "No MAC"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert models.Asset.objects.count() == 0


def test_upsert_token_auth(token_auth_client: APIClient) -> None:
    """PUT with Token auth header, assert 201."""
    response = _put_upsert(token_auth_client, SCANNER_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    assert netaddr.EUI(response.data["interface"]["mac_address"]) == netaddr.EUI(
        "00:03:b1:b5:b6:48"
    )
    assert models.Asset.objects.count() == 1


@pytest.mark.skip(reason="Blueflow uses AllowAny; auth enforced by consuming product")
def test_upsert_unauth_403(enable_core_switch: None) -> None:
    """PUT unauthenticated would assert 403 if IsAuthenticated were enforced."""
    client = APIClient()
    response = client.put(
        "/api/assets/upsert/",
        json.dumps(SCANNER_FULL_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert models.Asset.objects.count() == 0


def test_upsert_unknown_fields_dropped(asset_edit_client: APIClient) -> None:
    """connect_port_tcp and ipv6_address are silently dropped."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "ipv6_address": "::1",
        "connect_port_tcp": "9999",
    }
    response = _put_upsert(asset_edit_client, payload)
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get()
    assert asset.mac_address == "11:22:33:44:55:66"
    assert not hasattr(asset, "ipv6_address") or asset.ipv6_address is None
    assert not hasattr(asset, "connect_port_tcp")


def test_upsert_services_merge(asset_edit_client: APIClient) -> None:
    """Two upserts union their services; overlapping pairs stay one row."""
    payload1 = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "services": [
            {"port": 80, "protocol": "tcp"},
            {"port": 443, "protocol": "tcp"},
        ],
    }
    response1 = _put_upsert(asset_edit_client, payload1)
    assert response1.status_code == status.HTTP_201_CREATED

    payload2 = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "services": [
            {"port": 443, "protocol": "tcp"},
            {"port": 8080, "protocol": "tcp"},
        ],
    }
    response2 = _put_upsert(asset_edit_client, payload2)
    assert response2.status_code == status.HTTP_200_OK

    asset = models.Asset.objects.get(interface__mac_address="11:22:33:44:55:66")
    assert _service_pairs(asset) == {
        (80, "tcp"),
        (443, "tcp"),
        (8080, "tcp"),
    }


def test_upsert_services_cross_protocol_merge(asset_edit_client: APIClient) -> None:
    """A TCP-only asset gains UDP services on a follow-up upsert; both kept."""
    response1 = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "manufacturer": "Acme",
            "services": [{"port": 80, "protocol": "tcp"}],
        },
    )
    assert response1.status_code == status.HTTP_201_CREATED

    response2 = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "manufacturer": "Acme",
            "services": [
                {"port": 80, "protocol": "udp"},
                {"port": 53, "protocol": "udp"},
            ],
        },
    )
    assert response2.status_code == status.HTTP_200_OK

    asset = models.Asset.objects.get(interface__mac_address="11:22:33:44:55:66")
    assert _service_pairs(asset) == {(80, "tcp"), (80, "udp"), (53, "udp")}


def test_upsert_services_tcp_and_udp_coexist(asset_edit_client: APIClient) -> None:
    """The same port on TCP and UDP are two separate rows (e.g. DNS on 53)."""
    response = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "manufacturer": "Acme",
            "services": [
                {"port": 53, "protocol": "tcp"},
                {"port": 53, "protocol": "udp"},
            ],
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get(interface__mac_address="11:22:33:44:55:66")
    assert _service_pairs(asset) == {(53, "tcp"), (53, "udp")}


# ---------------------------------------------------------------------------
# Section 2: GET round-trip
# ---------------------------------------------------------------------------


def test_get_asset_by_id_after_upsert(asset_edit_client: APIClient) -> None:
    """PUT upsert, extract id, GET /api/assets/{id}/, assert 200 and fields match."""
    response = _put_upsert(asset_edit_client, SCANNER_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    asset_id = response.data["id"]
    get_response = asset_edit_client.get(f"/api/assets/{asset_id}/")
    assert get_response.status_code == status.HTTP_200_OK
    assert get_response.data["id"] == asset_id
    assert get_response.data["interface"]["ipv4"] == "10.0.0.155"
    assert get_response.data["name"] == "Infuse-O-Matic Peach B+"
    assert get_response.data["interface"]["mac_address"] == "00:03:b1:b5:b6:48"


def test_get_asset_after_upsert_404(asset_edit_client: APIClient) -> None:
    """GET /api/assets/99999/, assert 404."""
    response = asset_edit_client.get("/api/assets/99999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.skip(reason="Blueflow uses AllowAny; auth enforced by consuming product")
def test_get_asset_after_upsert_unauth_403(enable_core_switch: None) -> None:
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
    response = _put_upsert(asset_edit_client, SCANNER_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    list_response = asset_edit_client.get("/api/assets/")
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.data["count"] == 1
    results = list_response.data["results"]
    assert len(results) == 1
    assert results[0]["interface"]["mac_address"] == "00:03:b1:b5:b6:48"


@pytest.mark.skip(
    reason="django-simple-history update_change_reason filter fails with netfields"
)
def test_upsert_history_reason(asset_edit_client: APIClient) -> None:
    """PUT upsert with provenance/client_id/last_seen, assert history_change_reason."""
    response = _put_upsert(asset_edit_client, SCANNER_FULL_PAYLOAD)
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get()
    latest = asset.history.order_by("-history_date").first()
    assert latest is not None
    reason = latest.history_change_reason
    assert reason is not None
    assert "HL7 PRT-16" in reason
    assert "mymachine.example.com" in reason
    assert "2019-01-02" in reason


def test_upsert_oui_manufacturer_from_mac(asset_edit_client: APIClient) -> None:
    """PUT with registered OUI MAC.

    assert oui_manufacturer auto-populated from netaddr.
    """
    response = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "00:03:b1:b5:b6:48",
            "manufacturer": "Acme",
            "name": "Medical device",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    # OUI 00:03:b1 is registered; vendor may be Hospira, ICU Medical, etc.
    assert response.data["oui_manufacturer"] is not None
    assert len(response.data["oui_manufacturer"]) > 0
    asset = models.Asset.objects.get()
    assert asset.oui_manufacturer is not None


# ---------------------------------------------------------------------------
# Section 4: PUT semantics and validation
# ---------------------------------------------------------------------------


def test_upsert_put_idempotency(asset_edit_client: APIClient) -> None:
    """PUT same payload 3 times, assert only 1 asset exists."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "ip_address": "10.0.0.1",
    }
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
        "manufacturer": "Acme",
        "ipv4_address": "10.0.0.1",
        "identifier": "Legacy Device",
    }
    response = _put_upsert(asset_edit_client, payload)
    # Legacy fields are unknown to the serializer and silently dropped.
    # The asset is created with only mac_address.
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["interface"]["ipv4"] is None
    assert response.data["name"] == ""


def test_upsert_modern_field_names(asset_edit_client: APIClient) -> None:
    """PUT with canonical field names (ip_address, name) works directly."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "manufacturer": "Acme",
        "ip_address": "10.0.0.1",
        "name": "Modern Device",
    }
    response = _put_upsert(asset_edit_client, payload)
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["interface"]["ipv4"] == "10.0.0.1"
    assert response.data["name"] == "Modern Device"


def test_upsert_no_deprecation_header(asset_edit_client: APIClient) -> None:
    """PUT response does not include Deprecation header."""
    response = _put_upsert(
        asset_edit_client,
        {"mac_address": "11:22:33:44:55:66", "manufacturer": "Acme"},
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
    """PUT with out-of-range port in services returns 400."""
    response = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "services": [{"port": 70000, "protocol": "tcp"}],
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_upsert_non_numeric_port_400(asset_edit_client: APIClient) -> None:
    """PUT with non-integer port in services returns 400."""
    response = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "services": [{"port": "abc", "protocol": "tcp"}],
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_upsert_empty_protocol_400(asset_edit_client: APIClient) -> None:
    """PUT with empty-string protocol returns 400."""
    response = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "manufacturer": "Acme",
            "services": [{"port": 80, "protocol": ""}],
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_upsert_services_deduped(asset_edit_client: APIClient) -> None:
    """PUT with duplicate ``(port, protocol)`` pairs stores each pair once."""
    response = _put_upsert(
        asset_edit_client,
        {
            "mac_address": "11:22:33:44:55:66",
            "manufacturer": "Acme",
            "services": [
                {"port": 80, "protocol": "tcp"},
                {"port": 443, "protocol": "tcp"},
                {"port": 80, "protocol": "tcp"},
                {"port": 8080, "protocol": "tcp"},
                {"port": 443, "protocol": "tcp"},
            ],
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    asset = models.Asset.objects.get(interface__mac_address="11:22:33:44:55:66")
    assert _service_pairs(asset) == {(80, "tcp"), (443, "tcp"), (8080, "tcp")}
