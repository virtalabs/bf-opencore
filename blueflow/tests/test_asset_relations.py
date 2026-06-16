"""Asset tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

from blueflow import models

################################################################
#  Test routes for associated tables, e.g.,
#  "which networks does this asset belong to?"
#  (currently /api/assets/1/networks/, soon to be /api/networks/?asset=1)


# Many functions use Model classes which *do* have an 'objects' member

################
# Tags


def test_get_asset_tags_obsolete(auth_client):
    """Test old /api/assets/<n>/tags way to get tags associated with asset.

    NOTE: will remove this route; then change assertion to
          assert response.status_code == status.HTTP_404_NOT_FOUND (or 405)
    """
    asset = models.Asset.objects.create(hostname="foo.com")
    tag_red = models.Tag.objects.create(name="red", color="red")
    tag_green = models.Tag.objects.create(name="green", color="green")
    _ = models.Tag.objects.create(name="blue", color="blue")
    models.AssetTag.objects.create(tag=tag_red, asset=asset)
    models.AssetTag.objects.create(tag=tag_green, asset=asset)
    response = auth_client.get(f"/api/assets/{asset.pk}/tags/")
    tags = response.data["results"]
    assert len(tags) == 2
    assert {t["id"] for t in tags} == {tag_red.pk, tag_green.pk}


def test_get_asset_tags_new(auth_client):
    """Test new /api/tags/?asset=<n> way to get tags associated with asset."""
    asset = models.Asset.objects.create(hostname="foo.com")
    tag_red = models.Tag.objects.create(name="red", color="red")
    tag_green = models.Tag.objects.create(name="green", color="green")
    _ = models.Tag.objects.create(name="blue", color="blue")
    models.AssetTag.objects.create(tag=tag_red, asset=asset)
    models.AssetTag.objects.create(tag=tag_green, asset=asset)
    response = auth_client.get(f"/api/tags/?asset={asset.pk}")
    tags = response.data["results"]
    assert len(tags) == 2
    assert {t["id"] for t in tags} == {tag_red.pk, tag_green.pk}


################
# Networks


def test_get_asset_network_old_api(admin_client):
    """Ensure we can determine which assets belong in network.

    NOTE: will remove this route; then change assertion to
          assert response.status_code == status.HTTP_404_NOT_FOUND
    """
    asset = models.Asset.objects.create(ip_address="10.0.0.1")
    network = models.Network.objects.create()
    network.cidr = ["10.0.0.0/24"]
    response = admin_client.get(f"/api/assets/{asset.pk}/networks/")
    networks = response.data["results"]
    assert len(networks) == 1
    assert networks[0]["id"] == network.pk


def test_get_asset_network_new_api(admin_client):
    """Ensure we can determine which assets belong in network."""
    asset = models.Asset.objects.create(ip_address="10.0.0.1")
    _ = models.Asset.objects.create(ip_address="10.0.1.1")
    network_blue = models.Network.objects.create(name="blue")
    network_blue.cidr = ["10.0.0.0/24"]
    network_red = models.Network.objects.create(name="red")
    network_red.cidr = ["10.0.0.0/31"]
    dummy_network = models.Network.objects.create(name="dummy_1")
    dummy_network.cidr = ["10.0.1.0/24"]
    response = admin_client.get(f"/api/networks/?asset={asset.pk}")
    networks = response.data["results"]
    assert len(networks) == 2
    assert {n["id"] for n in networks} == {network_blue.pk, network_red.pk}
