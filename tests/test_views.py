"""Tests for blueflow views/API (mirrors blueflow/views)."""

from rest_framework import status


def test_api_assets_empty(auth_client):
    """Asset list is empty by default."""
    response = auth_client.get("/assets/")
    assert response.status_code == status.HTTP_200_OK
    if isinstance(response.data, list):
        assert len(response.data) == 0
    else:
        assert response.data["count"] == 0


def test_api_schema(client):
    """OpenAPI schema endpoint is reachable."""
    response = client.get("/schema/")
    assert response.status_code == status.HTTP_200_OK
