# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""Tests for bf_opencore views/API (mirrors bf_opencore/views)."""

import pytest


def test_api_assets_empty(auth_client):
    """Asset list is empty by default."""
    response = auth_client.get("/assets/")
    assert response.status_code == 200
    assert response.data["count"] == 0


def test_api_schema(client):
    """OpenAPI schema endpoint is reachable."""
    response = client.get("/schema/")
    assert response.status_code == 200
