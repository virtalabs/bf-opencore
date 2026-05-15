"""Tests for the minimal topology endpoint (#135)."""

from uuid import UUID

from rest_framework import status
from rest_framework.reverse import reverse


def test_reverse_topology():
    """Reverse blueflow:topology == /api/topology/."""
    assert reverse("blueflow:topology") == "/api/topology/"


def test_topology_endpoint_returns_minimal_contract(auth_client):
    """GET /api/topology/ returns 200 with all required root fields."""
    response = auth_client.get(reverse("blueflow:topology"))
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["schema_version"] == "0.1.0-minimal"
    assert isinstance(body["timestamp"], str)
    assert isinstance(body["assets"], list)
    assert isinstance(body["connections"], list)
    UUID(body["snapshot_id"])


def test_topology_empty_state(auth_client):
    """Empty topology returns 200 with empty assets/connections (no 404)."""
    response = auth_client.get(reverse("blueflow:topology"))
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["assets"] == []
    assert body["connections"] == []
