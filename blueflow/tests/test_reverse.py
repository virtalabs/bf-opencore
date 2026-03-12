"""Test that reverse URL lookup works as expected."""

import django
import pytest
from rest_framework.reverse import reverse

from blueflow import models

# models do have 'objects' member, but it's being lazy loaded


def test_reverse_asset_tags():
    """Reverse blueflow:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse("blueflow:asset-tags", args=[1])
    assert url == "/api/assets/1/tags/"


def test_reverse_group_single():
    """Reverse blueflow:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse("blueflow:group-detail", args=[1])
    assert url == "/api/groups/1/"


def test_reverse_group():
    """Reverse blueflow:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse("blueflow:group-list")
    assert url == "/api/groups/"


@pytest.mark.xfail(
    raises=django.urls.exceptions.NoReverseMatch,
    reason="Route /api/assets/1/groups/ doesn't exist (and shouldn't)",
)
def test_reverse_asset_groups():
    """Reverse blueflow:asset-groups == /api/asset/<i>/groups."""
    # import pdb ; pdb.set_trace()
    url = reverse("blueflow:asset-groups", args=[1])
    assert url == "/api/assets/1/groups/"


def test_asset_tags_api(auth_client):
    """API for tags associated with asset works."""
    asset_obj = models.Asset.objects.create()
    res = auth_client.get(f"/api/assets/{asset_obj.id}/tags/")
    assert res.status_code == 200
    assert res.json()["count"] == 0


def test_asset_groups_api(auth_client):
    """API for groups associated with asset does NOT work this way.

    (see test_groups.py)
    """
    asset_obj = models.Asset.objects.create()
    res = auth_client.get(f"/api/assets/{asset_obj.id}/groups/")
    assert res.status_code == 404
