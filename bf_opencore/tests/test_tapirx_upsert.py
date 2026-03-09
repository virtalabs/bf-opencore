"""Tapirx upsert contract tests.

Validates that Tapirx can POST to /api/assets/upsert/ and that assets
are retrievable via GET /api/assets/{id}/.
"""

import json

import pytest

from bf_opencore import models

# Full Tapirx payload per asset.go - used for contract tests
TAPIRX_FULL_PAYLOAD = {
    "ipv4_address": "10.0.0.155",
    "ipv6_address": "",
    "open_port_tcp": "2575",
    "connect_port_tcp": "2575",
    "mac_address": "00:03:b1:b5:b6:48",
    "identifier": "Infuse-O-Matic Peach B+",
    "provenance": "HL7 PRT-16",
    "last_seen": "2019-01-02T12:37:22.938687-08:00",
    "client_id": "mymachine.example.com",
}


def _post_upsert(client, payload):
    """POST payload to upsert endpoint."""
    return client.post(
        "/api/assets/upsert/",
        json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Section 1: Contract tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tapirx_upsert_create(asset_edit_client):
    """POST full Tapirx payload, assert 201, verify ip_address, name, open_ports_tcp."""
    response = _post_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == 201
    assert response.data["ip_address"] == "10.0.0.155"
    assert response.data["name"] == "Infuse-O-Matic Peach B+"
    assert response.data["open_ports_tcp"] == [2575]
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
def test_tapirx_upsert_update(asset_edit_client):
    """POST twice same MAC, assert 200 on second, verify field update."""
    payload1 = {
        "mac_address": "11:22:33:44:55:66",
        "ipv4_address": "10.0.0.1",
        "identifier": "Original Name",
    }
    response1 = _post_upsert(asset_edit_client, payload1)
    assert response1.status_code == 201

    payload2 = {
        "mac_address": "11:22:33:44:55:66",
        "ipv4_address": "10.0.0.2",
        "identifier": "Updated Name",
    }
    response2 = _post_upsert(asset_edit_client, payload2)
    assert response2.status_code == 200
    assert response2.data["ip_address"] == "10.0.0.2"
    assert response2.data["name"] == "Updated Name"
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
def test_tapirx_upsert_minimal(asset_edit_client):
    """POST only mac_address, assert 201."""
    response = _post_upsert(asset_edit_client, {"mac_address": "00:03:b1:b5:b6:48"})
    assert response.status_code == 201
    assert response.data["mac_address"] == "00:03:b1:b5:b6:48"
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
def test_tapirx_upsert_no_mac_412(asset_edit_client):
    """POST without mac_address, assert 412."""
    response = _post_upsert(
        asset_edit_client,
        {"ipv4_address": "10.0.0.1", "identifier": "No MAC"},
    )
    assert response.status_code == 412
    assert models.Asset.objects.count() == 0


@pytest.mark.django_db
def test_tapirx_upsert_token_auth(tapirx_token_client):
    """POST with tapirx_token_client (Token header), assert 201."""
    response = _post_upsert(tapirx_token_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == 201
    assert response.data["mac_address"] == "00:03:b1:b5:b6:48"
    assert models.Asset.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.skip(reason="Open-core uses AllowAny; auth enforced by consuming product")
def test_tapirx_upsert_unauth_403(db, enable_core_switch):
    """POST unauthenticated would assert 403 if IsAuthenticated were enforced."""
    from rest_framework.test import APIClient

    client = APIClient()
    response = client.post(
        "/api/assets/upsert/",
        json.dumps(TAPIRX_FULL_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == 403
    assert models.Asset.objects.count() == 0


@pytest.mark.django_db
def test_tapirx_upsert_ignored_fields(asset_edit_client):
    """connect_port_tcp and ipv6_address are silently dropped."""
    payload = {
        "mac_address": "11:22:33:44:55:66",
        "ipv6_address": "::1",
        "connect_port_tcp": "9999",
    }
    response = _post_upsert(asset_edit_client, payload)
    assert response.status_code == 201
    asset = models.Asset.objects.get()
    assert asset.mac_address == "11:22:33:44:55:66"
    assert not hasattr(asset, "ipv6_address") or asset.ipv6_address is None
    assert not hasattr(asset, "connect_port_tcp")


@pytest.mark.django_db
def test_tapirx_upsert_open_port_appends(asset_edit_client):
    """POST twice with different open_port_tcp, verify both in open_ports_tcp."""
    payload1 = {
        "mac_address": "11:22:33:44:55:66",
        "open_port_tcp": "80",
    }
    response1 = _post_upsert(asset_edit_client, payload1)
    assert response1.status_code == 201
    assert response1.data["open_ports_tcp"] == [80]

    payload2 = {
        "mac_address": "11:22:33:44:55:66",
        "open_port_tcp": "443",
    }
    response2 = _post_upsert(asset_edit_client, payload2)
    assert response2.status_code == 200
    assert set(response2.data["open_ports_tcp"]) == {80, 443}
    asset = models.Asset.objects.get()
    assert set(asset.open_ports_tcp) == {80, 443}


# ---------------------------------------------------------------------------
# Section 2: GET round-trip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_asset_by_id_after_upsert(asset_edit_client):
    """POST upsert, extract id, GET /api/assets/{id}/, assert 200 and fields match."""
    response = _post_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == 201
    asset_id = response.data["id"]
    get_response = asset_edit_client.get(f"/api/assets/{asset_id}/")
    assert get_response.status_code == 200
    assert get_response.data["id"] == asset_id
    assert get_response.data["ip_address"] == "10.0.0.155"
    assert get_response.data["name"] == "Infuse-O-Matic Peach B+"
    assert get_response.data["mac_address"] == "00:03:b1:b5:b6:48"


@pytest.mark.django_db
def test_get_asset_after_upsert_404(asset_edit_client):
    """GET /api/assets/99999/, assert 404."""
    response = asset_edit_client.get("/api/assets/99999/")
    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.skip(reason="Open-core uses AllowAny; auth enforced by consuming product")
def test_get_asset_after_upsert_unauth_403(db, enable_core_switch):
    """GET without auth would assert 403 if IsAuthenticated were enforced."""
    from rest_framework.test import APIClient

    asset = models.Asset.objects.create(mac_address="aa:bb:cc:dd:ee:ff")
    client = APIClient()
    response = client.get(f"/api/assets/{asset.id}/")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Section 3: Functional
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_upsert_then_list(asset_edit_client):
    """POST upsert, GET /api/assets/, assert count=1 and asset in results."""
    response = _post_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == 201
    list_response = asset_edit_client.get("/api/assets/")
    assert list_response.status_code == 200
    assert list_response.data["count"] == 1
    results = list_response.data["results"]
    assert len(results) == 1
    assert results[0]["mac_address"] == "00:03:b1:b5:b6:48"


@pytest.mark.django_db
@pytest.mark.skip(
    reason="django-simple-history update_change_reason filter fails with netfields"
)
def test_upsert_history_reason(asset_edit_client):
    """POST upsert with provenance/client_id/last_seen, assert history_change_reason."""
    response = _post_upsert(asset_edit_client, TAPIRX_FULL_PAYLOAD)
    assert response.status_code == 201
    asset = models.Asset.objects.get()
    latest = asset.history.order_by("-history_date").first()
    assert latest is not None
    reason = latest.history_change_reason
    assert reason is not None
    assert "HL7 PRT-16" in reason
    assert "mymachine.example.com" in reason
    assert "2019-01-02" in reason


@pytest.mark.django_db
def test_upsert_nic_vendor_from_mac(asset_edit_client):
    """POST with registered OUI MAC, assert nic_vendor auto-populated from netaddr."""
    response = _post_upsert(
        asset_edit_client,
        {"mac_address": "00:03:b1:b5:b6:48", "identifier": "Medical device"},
    )
    assert response.status_code == 201
    # OUI 00:03:b1 is registered; vendor may be Hospira, ICU Medical, etc.
    assert response.data["nic_vendor"] is not None
    assert len(response.data["nic_vendor"]) > 0
    asset = models.Asset.objects.get()
    assert asset.nic_vendor is not None
