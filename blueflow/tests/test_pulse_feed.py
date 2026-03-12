"""Test pulse feed items, getting and modifying.

With special focus on perms.
"""

import json

import pytest

from blueflow import models


def test_get_pulse_feed_items(auth_client, pulse_feed_items):
    """Check that we can get all pulse feed items."""
    response = auth_client.get("/api/pulse/")
    assert response.status_code == 200
    pulse_feed_items = response.data["results"]
    assert len(pulse_feed_items) == 3


def test_get_one_pulse_feed_item(auth_client, pulse_feed_items):
    """Check that we can get one pulse feed item by its external ID."""
    pfi = models.PulseFeedItem.objects.first()
    response = auth_client.get(f"/api/pulse/{pfi.external_pulse_id}/")
    assert response.status_code == 200
    pulse_feed_item = response.data
    assert pulse_feed_item["id"] == pfi.id


def test_delete_pulse_feed_item(pulse_feed_auth_client, pulse_feed_items):
    """Make sure that we can't delete a pulse feed item."""
    pfi = models.PulseFeedItem.objects.first()
    response = pulse_feed_auth_client.delete(f"/api/pulse/{pfi.external_pulse_id}/")
    assert response.status_code == 403  # forbidden


def test_close_pulse_feed_item(pulse_feed_auth_client, pulse_feed_items):
    """Check that we can mark a pulse feed item as Closed."""
    pfi = models.PulseFeedItem.objects.first()
    assert pfi.status == "open"
    response = pulse_feed_auth_client.patch(
        f"/api/pulse/{pfi.external_pulse_id}/",
        json.dumps({"status": "closed"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    pfi = models.PulseFeedItem.objects.get(pk=pfi.id)
    assert pfi.status == "closed"


def test_delete_pulse_feed_item_unauth(auth_client, pulse_feed_items):
    """Make sure unauthorized can't delete a pulse feed item."""
    pfi = models.PulseFeedItem.objects.first()
    response = auth_client.delete(f"/api/pulse/{pfi.external_pulse_id}/")
    assert response.status_code == 403  # forbidden


@pytest.mark.xfail(reason="Blueflow has no role-based write permissions")
def test_close_pulse_feed_item_unauth(auth_client, pulse_feed_items):
    """Make sure unauthorized can't mark a pulse feed item as Closed."""
    pfi = models.PulseFeedItem.objects.first()
    assert pfi.status == "open"
    response = auth_client.patch(
        f"/api/pulse/{pfi.external_pulse_id}/",
        json.dumps({"status": "closed"}),
        content_type="application/json",
    )
    assert response.status_code == 403  # forbidden
