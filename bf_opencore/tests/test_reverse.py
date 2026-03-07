"""Test that reverse URL lookup works as expected."""

import django
import pytest
from rest_framework.reverse import reverse

from bf_opencore import models

# models do have 'objects' member, but it's being lazy loaded


@pytest.mark.django_db
def test_reverse_asset_tags():
    """Reverse bf_opencore:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse("bf_opencore:asset-tags", args=[1])
    assert url == "/api/assets/1/tags/"


@pytest.mark.django_db
def test_reverse_group_single():
    """Reverse bf_opencore:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse("bf_opencore:group-detail", args=[1])
    assert url == "/api/groups/1/"


@pytest.mark.django_db
def test_reverse_group():
    """Reverse bf_opencore:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse("bf_opencore:group-list")
    assert url == "/api/groups/"


@pytest.mark.django_db
@pytest.mark.xfail(
    raises=django.urls.exceptions.NoReverseMatch,
    reason="Route /api/assets/1/groups/ doesn't exist (and shouldn't)",
)
def test_reverse_asset_groups():
    """Reverse bf_opencore:asset-groups == /api/asset/<i>/groups."""
    # import pdb ; pdb.set_trace()
    url = reverse("bf_opencore:asset-groups", args=[1])
    assert url == "/api/assets/1/groups/"


@pytest.mark.django_db
def test_asset_tags_api(auth_client):
    """API for tags associated with asset works."""
    asset_obj = models.Asset.objects.create()
    res = auth_client.get(f"/api/assets/{asset_obj.id}/tags/")
    assert res.status_code == 200
    assert res.json()["count"] == 0


@pytest.mark.django_db
def test_asset_groups_api(auth_client):
    """API for groups associated with asset does NOT work this way.

    (see test_groups.py)
    """
    asset_obj = models.Asset.objects.create()
    res = auth_client.get(f"/api/assets/{asset_obj.id}/groups/")
    assert res.status_code == 404

