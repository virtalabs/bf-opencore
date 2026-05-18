"""Tests for the Asset.usage serializer field (contract-level stub).

The usage field is a 7-element array indexed by Python's datetime.weekday()
convention: 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday,
5=Saturday, 6=Sunday.
"""

from rest_framework import status

from blueflow import models

DAYS_IN_WEEK = 7


def test_asset_response_includes_usage_field(auth_client):
    """Each asset response includes a usage field as a 7-element array."""
    asset = models.Asset.objects.create(hostname="usage-test.example.com")
    response = auth_client.get(f"/api/assets/{asset.id}/")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert "usage" in body
    assert isinstance(body["usage"], list)
    assert len(body["usage"]) == DAYS_IN_WEEK


def test_asset_usage_stub_emits_empty_hour_dicts(auth_client):
    """Stub usage returns an empty hour dict at every weekday index."""
    asset = models.Asset.objects.create(hostname="usage-empty.example.com")
    response = auth_client.get(f"/api/assets/{asset.id}/")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    for index, hours in enumerate(body["usage"]):
        assert hours == {}, f"index {index} should be empty in stub (got {hours!r})"
