"""Tests for the Asset.usage serializer field (contract-level stub)."""

from rest_framework import status

from blueflow import models


def test_asset_response_includes_usage_field(auth_client):
    """Each asset response includes a usage field with all seven weekdays."""
    asset = models.Asset.objects.create(hostname="usage-test.example.com")
    response = auth_client.get(f"/api/assets/{asset.id}/")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert "usage" in body

    expected_days = {
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
    }
    assert set(body["usage"].keys()) == expected_days


def test_asset_usage_stub_emits_empty_hour_dicts(auth_client):
    """Stub usage returns empty hour dicts for every weekday."""
    asset = models.Asset.objects.create(hostname="usage-empty.example.com")
    response = auth_client.get(f"/api/assets/{asset.id}/")
    body = response.json()
    for day, hours in body["usage"].items():
        assert hours == {}, f"{day} should be empty dict in stub (got {hours!r})"
