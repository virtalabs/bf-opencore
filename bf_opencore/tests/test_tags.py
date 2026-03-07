"""Tagging tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import json

import pytest

from bf_opencore import models

# Many functions use Model classes which *do* have an 'objects' member


@pytest.mark.django_db
def test_tag_asset_via_model(auth_client):
    """Tagging an asset adds tag info to an asset record."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    asset = auth_client.get(f"/api/assets/{asset_obj.id}/").json()
    assert asset["hostname"] == "foo.com"
    assert asset["asset_tags"] == []

    tag = models.Tag.objects.create(name="red", color="red")
    asset_tag = models.AssetTag.objects.create(tag=tag, asset=asset_obj)
    assert list(asset_obj.tags.all()) == [tag]
    assert list(asset_obj.asset_tags.all()) == [asset_tag]

    asset = auth_client.get(f"/api/assets/{asset_obj.id}/").json()
    assert len(asset["asset_tags"]) == 1
    assert asset["asset_tags"].pop()["tag"]["id"] == tag.id


@pytest.mark.django_db
def test_tag_asset_via_api(biomed_client):
    """Admin can tag assets through assets/N/tags."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    tag = models.Tag.objects.create(name="red", color="red")
    resp = biomed_client.post(
        f"/api/assets/{asset_obj.id}/tags/",
        json.dumps({"tag_id": tag.id}),
        content_type="application/json",
    )
    assert resp.status_code == 201  # created
    assert list(asset_obj.tags.all()) == [tag]


@pytest.mark.django_db
def test_tag_asset_via_api_failing(biomed_client):
    """Try to tag assets through /api/assettags/.

    This *does not work* and we're not really sure why.  I'm sure it can
    be fixed, but it seems equally natural to allow adding tags via the
    /api/assets/<N>/tags/ route as in the test function just above.
    """
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    tag = models.Tag.objects.create(name="red", color="red")
    resp = biomed_client.post(
        "/api/assettags/",
        json.dumps({"tag_id": tag.id, "asset_id": asset_obj.id}),
        content_type="application/json",
    )
    assert resp.status_code == 201  # created
    assert list(asset_obj.tags.all()) == [tag]


@pytest.mark.django_db
def test_get_assettag_via_api(biomed_client):
    """Admin can tag assets through assets/N/tags."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    tag = models.Tag.objects.create(name="red", color="red")
    dummy_asset_tag = models.AssetTag.objects.create(tag=tag, asset=asset_obj)
    resp = biomed_client.get("/api/assettags/")
    asset_tags = resp.json()["results"]
    assert len(asset_tags) == 1
    assert asset_tags[0]["asset_id"] == asset_obj.id
    assert asset_tags[0]["tag"]["id"] == tag.id


@pytest.mark.django_db
def test_untag_asset_via_api(biomed_client):
    """Biomed can untag assets."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    tag = models.Tag.objects.create(name="red", color="red")
    asset_tag = models.AssetTag.objects.create(tag=tag, asset=asset_obj)
    resp = biomed_client.delete(f"/api/assettags/{asset_tag.id}/")
    assert resp.status_code == 204  # no content
    assert list(asset_obj.tags.all()) == []


@pytest.mark.django_db
def test_create_tag(auth_client, biomed_client):
    """Biomed can create tags via API."""
    # invalid hexadecimal color code
    resp = biomed_client.post(
        "/api/tags/",
        json.dumps({"name": "red", "color": "red"}),
        content_type="application/json",
    )
    assert resp.status_code == 400  # bad request

    resp2 = biomed_client.post(
        "/api/tags/",
        json.dumps({"name": "grn", "color": "00ff00"}),
        content_type="application/json",
    )
    assert resp2.status_code == 201  # created
    resp = auth_client.get("/api/tags/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    tags = resp.json()["results"]
    assert len(tags) == 1
    assert tags[0]["name"] == "grn"
    assert tags[0]["color"] == "#00ff00"


@pytest.mark.django_db
@pytest.mark.parametrize("num_tags", [0, 1, 20, 21, 100])
def test_create_many_tags(num_tags, auth_client, biomed_client):
    """Biomed can create tags via API."""
    resp = auth_client.get("/api/tags/")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert len(resp.json()["results"]) == 0
    kwargs = {"content_type": "application/json"}
    for n in range(num_tags):
        kwargs["data"] = json.dumps({"name": f"tag_{n}", "color": "00ff00"})
        resp = biomed_client.post("/api/tags/", **kwargs)
        assert resp.status_code == 201  # created
    resp = auth_client.get("/api/tags/")
    assert resp.status_code == 200
    assert resp.json()["count"] == num_tags
    assert len(resp.json()["results"]) == num_tags


@pytest.mark.django_db
@pytest.mark.xfail(reason="Open-core has no role-based write permissions")
def test_tag_asset_via_api_reg_user(auth_client):
    """Non-admin, non-biomed client cannot tag assets."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    tag = models.Tag.objects.create(name="red", color="red")
    resp = auth_client.post(
        f"/api/assets/{asset_obj.id}/tags/",
        json.dumps({"tag_id": tag.id}),
        content_type="application/json",
    )
    assert resp.status_code == 403  # forbidden


@pytest.mark.django_db
@pytest.mark.xfail(reason="Open-core has no role-based write permissions")
def test_untag_asset_via_api_reg_user(auth_client):
    """Non-admin, non-biomed client cannot untag assets."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    tag = models.Tag.objects.create(name="red", color="red")
    asset_tag = models.AssetTag.objects.create(tag=tag, asset=asset_obj)
    resp = auth_client.delete(f"/api/assettags/{asset_tag.id}/")
    assert resp.status_code == 403  # forbidden


@pytest.mark.django_db
@pytest.mark.xfail(reason="Open-core has no role-based write permissions")
def test_create_tag_reg_user(auth_client):
    """Non-admin, non-biomed client cannot create tags via API."""
    # invalid hexadecimal color code
    resp = auth_client.post(
        "/api/tags/",
        json.dumps({"name": "red", "color": "ff0000"}),
        content_type="application/json",
    )
    assert resp.status_code == 403  # bad request


@pytest.mark.django_db
def test_create_tag_biomed_user(biomed_client):
    """Non-admin biomed client can create tags via API."""
    # invalid hexadecimal color code
    resp = biomed_client.post(
        "/api/tags/",
        json.dumps({"name": "red", "color": "ff0000"}),
        content_type="application/json",
    )
    assert resp.status_code == 201  # created


@pytest.mark.django_db
def test_get_tagged_asset_obsolete(auth_client):
    """Test a route that's now obsolete."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    _ = models.Asset.objects.create(hostname="spam.com")
    tag = models.Tag.objects.create(name="red", color="red")
    models.AssetTag.objects.create(tag=tag, asset=asset_obj)
    response = auth_client.get(f"/api/tags/{tag.id}/assets/")
    assert response.status_code == 405
    assert response.status_text == "Method Not Allowed"


@pytest.mark.django_db
def test_get_tagged_asset_new(auth_client):
    """Test new API route."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    _ = models.Asset.objects.create(hostname="spam.com")
    tag = models.Tag.objects.create(name="red", color="red")
    models.AssetTag.objects.create(tag=tag, asset=asset_obj)
    response = auth_client.get(f"/api/assets/?tag={tag.id}")
    assets = response.data["results"]
    assert len(assets) == 1  # This fails; 2 assets are returned.
    assert assets[0]["id"] == asset_obj.id
