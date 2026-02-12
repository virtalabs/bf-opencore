"""Test that reverse URL lookup works as expected."""

import pytest
import django
from rest_framework.reverse import reverse
import bf_opencore.models as bf_mod

# bf_mod models do have 'objects' member, but it's being lazy loaded


def test_reverse_asset_tags():
    """Reverse api:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse('api:asset-tags', args=[1])
    assert url == '/api/assets/1/tags/'


def test_reverse_group_single():
    """Reverse api:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse('api:group-detail', args=[1])
    assert url == '/api/groups/1/'


def test_reverse_group():
    """Reverse api:asset-tags == /api/asset/<i>/tags."""
    # import pdb ; pdb.set_trace()
    url = reverse('api:group-list')
    assert url == '/api/groups/'


@pytest.mark.xfail(
    raises=django.urls.exceptions.NoReverseMatch,
    reason="Route /api/assets/1/groups/ doesn't exist (and shouldn't)")
def test_reverse_asset_groups():
    """Reverse api:asset-groups == /api/asset/<i>/groups."""
    # import pdb ; pdb.set_trace()
    url = reverse('api:asset-groups', args=[1])
    assert url == '/api/assets/1/groups/'


def test_asset_tags_api(auth_client):
    """API for tags associated with asset works."""
    asset_obj = bf_mod.Asset.objects.create()
    res = auth_client.get('/api/assets/{}/tags/'.format(asset_obj.id))
    assert res.status_code == 200
    assert res.json()['count'] == 0


def test_asset_groups_api(auth_client):
    """API for groups associated with asset does NOT work this way.

    (see test_groups.py)
    """
    asset_obj = bf_mod.Asset.objects.create()
    res = auth_client.get('/api/assets/{}/groups/'.format(asset_obj.id))
    assert res.status_code == 404


def test_reverse_remediable_list():
    """Reverse api:remediable-list == /api/remediable/."""
    url = reverse('api:assetriskfactorremediable-list')
    assert url == '/api/assetriskfactorremediables/'


def test_reverse_remediable_detail():
    """Reverse api:remediable-detail == /api/remediable/<i>/."""
    url = reverse('api:assetriskfactorremediable-detail', args=[1])
    assert url == '/api/assetriskfactorremediables/1/'
