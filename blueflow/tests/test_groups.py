"""Test group access."""

import json

import pytest

from rest_framework import status

from blueflow import models


def test_get_asset_groups_obsolete(auth_client, asset_groups):
    """Test old /api/assets/<n>/groups way to get groups with asset.

    NOTE: will remove this route; then change assertion to
          assert response.status_code == status.HTTP_404_NOT_FOUND (or 405)
    """
    response = auth_client.get(f"/api/assets/{asset_groups.aa.id}/groups/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_groups_for_asset_new(auth_client, asset_groups):
    """Get groups that asset is member of."""
    response = auth_client.get(f"/api/groups/?asset={asset_groups.aa.id}")
    groups = response.data["results"]
    assert len(groups) == 2  # noqa: PLR2004
    assert {t["id"] for t in groups} == {asset_groups.gr.id, asset_groups.gg.id}


def test_get_group_assets(auth_client, asset_groups):
    """Get assets belonging to group."""
    response = auth_client.get(f"/api/assets/?group={asset_groups.gg.id}")
    assets = response.data["results"]
    assert len(assets) == 2  # noqa: PLR2004
    assert {a["id"] for a in assets} == {asset_groups.aa.id, asset_groups.ab.id}


# Get asset groups


def test_get_asset_groups(auth_client, asset_groups):
    """Get all asset groups."""
    # fixture asset_groups to set up data, but don't need to access.
    response = auth_client.get("/api/assetgroups/")
    agroups = response.data["results"]
    assert len(agroups) == 3  # noqa: PLR2004


def test_get_one_asset_group_by_id(admin_client, asset_groups):
    """Get one asset group."""
    response = admin_client.get(f"/api/assetgroups/{asset_groups.agra.id}/")
    assert response.status_code == status.HTTP_200_OK
    agroup = response.data
    assert agroup["id"] == asset_groups.agra.id


def test_get_asset_asset_groups(auth_client, asset_groups):
    """Get asset groups for one asset."""
    response = auth_client.get(f"/api/assetgroups/?asset={asset_groups.aa.id}")
    agroups = response.data["results"]
    assert len(agroups) == 2  # noqa: PLR2004
    assert {g["id"] for g in agroups} == {asset_groups.agra.id, asset_groups.agga.id}


def test_get_no_asset_asset_groups(auth_client, asset_groups):
    """Get no asset groups for nonexistent asset."""
    # fixture asset_groups to set up data, but don't need to access.
    response = auth_client.get(f"/api/assetgroups/?asset={9999}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_group_asset_groups(auth_client, asset_groups):
    """Get asset groups for one group."""
    response = auth_client.get(f"/api/assetgroups/?group={asset_groups.gg.id}")
    agroups = response.data["results"]
    assert len(agroups) == 2  # noqa: PLR2004
    assert {g["id"] for g in agroups} == {asset_groups.agga.id, asset_groups.aggb.id}


def test_get_no_group_asset_groups(auth_client, asset_groups):
    """Get no asset groups for nonexistent group."""
    # fixture asset_groups to set up data, but don't need to access.
    response = auth_client.get(f"/api/assetgroups/?group={9999}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_asset_group_by_group_plus_asset(admin_client, asset_groups):
    """Get asset group for one asset/group combo."""
    response = admin_client.get(
        f"/api/assetgroups/?asset={asset_groups.aa.id}&group={asset_groups.gr.id}"
    )
    agroups = response.data["results"]
    assert len(agroups) == 1
    assert agroups[0]["id"] == asset_groups.agra.id


# Delete asset groups


def test_delete_all_asset_groups(admin_client, asset_groups):
    """Delete all asset groups."""
    # fixture asset_groups to set up data, but don't need to access.
    response = admin_client.delete("/api/assetgroups/")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert response.data["detail"].startswith(
        "To DELETE one AssetGroup, specify both 'asset' and 'group'."
    )


def test_delete_one_asset_group_by_id(admin_client, asset_groups):
    """Delete one asset group."""
    response = admin_client.delete(f"/api/assetgroups/{asset_groups.agga.id}/")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.data is None
    response = admin_client.get("/api/assetgroups/")
    agroups = response.data["results"]
    assert len(agroups) == 2  # noqa: PLR2004
    assert {ag["id"] for ag in agroups} == {asset_groups.agra.id, asset_groups.aggb.id}


def test_delete_asset_group_by_asset_only_fails(admin_client, asset_groups):
    """Delete one asset group by asset only should fail.

    Want to prevent DELETE /api/assetgroups/?asset={} from working (it
    could conceivably work if there's only one group for that asset.)
    """
    # asset b belongs to only one group, thus the query below pertains
    # to only one assetgroup.  Still, we want to be strict and only
    # allow deletion if the groop, too, is provided.
    response = admin_client.delete(f"/api/assetgroups/?asset={asset_groups.ab.id}")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_delete_asset_group_by_group_plus_asset(admin_client, asset_groups):
    """Delete one asset group by group + asset combo."""
    response = admin_client.delete(
        f"/api/assetgroups/?asset={asset_groups.aa.id}&group={asset_groups.gg.id}"
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.data is None
    response = admin_client.get("/api/assetgroups/")
    agroups = response.data["results"]
    assert len(agroups) == 2  # noqa: PLR2004
    ag_ids = {
        asset_groups.agra.id,
        # asset_groups.agga.id,
        asset_groups.aggb.id,
    }
    assert {ag["id"] for ag in agroups} == ag_ids


# Create group


def test_create_group_admin(biomed_client, admin_client):
    """Create a group.

    This works, but only because we use an 'admin_client'.  Plain old
    'auth_client' is *not* allowed to create a group.  We want a
    "biomed_client" to be allowed to create groups, and add assets to
    it, etc.  In order to do this, we create a new "user group" called
    'blueflow-asset-group-edit'.
    """
    resp = admin_client.post(
        "/api/groups/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert resp.status_code == status.HTTP_201_CREATED  # created
    resp = biomed_client.get("/api/groups/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 1
    groups = resp.json()["results"]
    assert len(groups) == 1
    assert groups[0]["name"] == "spam"


@pytest.mark.xfail(reason="Blueflow has no role-based write permissions")
def test_create_group_auth(auth_client):
    """Create a group with auth client should *not* work."""
    resp = auth_client.post(
        "/api/groups/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN  # forbidden


def test_create_group_biomed(biomed_client):
    """Create a group with a 'biomed_client'."""
    resp = biomed_client.post(
        "/api/groups/", json.dumps({"name": "spam"}), content_type="application/json"
    )
    assert resp.status_code == status.HTTP_201_CREATED  # created
    resp = biomed_client.get("/api/groups/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 1
    groups = resp.json()["results"]
    assert len(groups) == 1
    assert groups[0]["name"] == "spam"


def test_delete_group_biomed(biomed_client):
    """Delete a group with a 'biomed_client'."""
    group_obj = models.Group.objects.create(name="spam")
    resp = biomed_client.delete(f"/api/groups/{group_obj.id}/")
    assert resp.status_code == status.HTTP_204_NO_CONTENT  # deleted


def test_create_asset_group(biomed_client):
    """Add asset(s) to a group AKA create assetgroup."""
    gid = models.Group.objects.create(name="spam").id
    aid1 = models.Asset.objects.create(hostname="eggs").id
    aid2 = models.Asset.objects.create(hostname="ham").id
    resp = biomed_client.post(
        f"/api/groups/{gid}/assets/",
        json.dumps({"asset_ids": [aid1, aid2]}),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_201_CREATED  # created
    response = biomed_client.get("/api/assetgroups/")
    agroups = response.data["results"]
    assert len(agroups) == 2  # noqa: PLR2004


def test_delete_asset_group(biomed_client):
    """Remove asset from group AKA delete assetgroup.

    Duplicate of test_delete_asset_group_by_group_plus_asset except
    we're using a 'biomed client'.
    """
    gid = models.Group.objects.create(name="spam").id
    aid = models.Asset.objects.create(hostname="eggs").id
    _ = models.AssetGroup.objects.create(group_id=gid, asset_id=aid)
    response = biomed_client.get("/api/assetgroups/")
    agroups = response.data["results"]
    assert len(agroups) == 1
    resp = biomed_client.delete(f"/api/assetgroups/?asset={aid}&group={gid}")
    assert resp.status_code == status.HTTP_204_NO_CONTENT  # deleted
    response = biomed_client.get("/api/assetgroups/")
    agroups = response.data["results"]
    assert len(agroups) == 0
