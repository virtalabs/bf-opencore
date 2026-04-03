"""Test saved search, setting, getting and modifying.

With special focus on perms.
"""

import json

import pytest

from rest_framework import status

from blueflow import models


def test_search(auth_client, acme_assets):
    """Verify that regular boring search works."""
    candidates = auth_client.get("/api/assets/?search=acme")
    assert candidates.data["count"] == 2  # noqa: PLR2004


def test_save_search(asset_edit_client, acme_assets):
    """Verify that we can save a search."""
    assert models.SavedSearch.objects.count() == 0
    save_search_data = {"name": "Search for Acme", "search_query": [["search", "acme"]]}
    resp = asset_edit_client.post(
        "/api/savedsearches/",
        json.dumps(save_search_data),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert models.SavedSearch.objects.count() == 1
    saved_search = models.SavedSearch.objects.first()
    assert saved_search.name == save_search_data["name"]
    assert saved_search.search_query == save_search_data["search_query"]


def test_save_search_any_user(auth_client, acme_assets):
    """Verify that any client can save a search."""
    assert models.SavedSearch.objects.count() == 0
    save_search_data = {"name": "Search for Acme", "search_query": [["search", "acme"]]}
    resp = auth_client.post(
        "/api/savedsearches/",
        json.dumps(save_search_data),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert models.SavedSearch.objects.count() == 1


@pytest.mark.xfail(
    raises=AssertionError, reason="Want to prevent deletion but not doing it yet."
)
def test_delete_saved_search(auth_client):
    """Unauthorized users shouldn't be allowed to delete saved search."""
    save_search_data = {"name": "Search for Acme", "search_query": [["search", "acme"]]}
    ss = models.SavedSearch.objects.create(**save_search_data)
    resp = auth_client.delete(f"/api/savedsearches/{ss.id}/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.xfail(
    raises=AssertionError, reason="Want to prevent editing but not doing it yet."
)
def test_edit_saved_search(auth_client):
    """Unauthorized users shouldn't be allowed to delete saved search."""
    save_search_data = {"name": "Search for Acme", "search_query": [["search", "acme"]]}
    ss = models.SavedSearch.objects.create(**save_search_data)
    resp = auth_client.patch(
        f"/api/savedsearches/{ss.id}/",
        json.dumps({"search_query": [["search", "akm"]]}),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    saved_search = models.SavedSearch.objects.first()
    assert saved_search.name == save_search_data["name"]
    assert saved_search.search_query[0][1] == "acme"


def test_get_saved_search_one(auth_client):
    """Ensure not otherwise authorized client can get a saved search."""
    save_search_data = {"name": "Search for Acme", "search_query": [["search", "acme"]]}
    models.SavedSearch.objects.create(**save_search_data)
    resp = auth_client.get("/api/savedsearches/")
    assert resp.status_code == status.HTTP_200_OK
    results = resp.data["results"]
    assert len(results) == 1
    saved_search = results[0]
    assert saved_search["name"] == save_search_data["name"]
    assert saved_search["search_query"] == save_search_data["search_query"]


def test_get_saved_search_many(auth_client):
    """Ensure not otherwise authorized client can get list of saved search."""
    save_search_data = {"name": "Search for Acme", "search_query": [["search", "acme"]]}
    models.SavedSearch.objects.create(**save_search_data)
    save_search_data = {"name": "Search for Spam", "search_query": [["search", "spam"]]}
    models.SavedSearch.objects.create(**save_search_data)
    save_search_data = {"name": "Search for Eggs", "search_query": [["search", "eggs"]]}
    models.SavedSearch.objects.create(**save_search_data)
    resp = auth_client.get("/api/savedsearches/")
    assert resp.status_code == status.HTTP_200_OK
    assert len(resp.data["results"]) == 3  # noqa: PLR2004
