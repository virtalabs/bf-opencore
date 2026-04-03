"""Asset tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""


from blueflow import models
from rest_framework import status

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
    dummy_tag = models.Tag.objects.create(name="blue", color="blue")
    models.AssetTag.objects.create(tag=tag_red, asset=asset)
    models.AssetTag.objects.create(tag=tag_green, asset=asset)
    response = auth_client.get(f"/api/assets/{asset.pk}/tags/")
    # assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    # assert response.status_text == "Method Not Allowed"
    tags = response.data["results"]
    assert len(tags) == 2  # noqa: PLR2004
    assert {t["id"] for t in tags} == {tag_red.pk, tag_green.pk}


def test_get_asset_tags_new(auth_client):
    """Test new /api/tags/?asset=<n> way to get tags associated with asset."""
    asset = models.Asset.objects.create(hostname="foo.com")
    tag_red = models.Tag.objects.create(name="red", color="red")
    tag_green = models.Tag.objects.create(name="green", color="green")
    dummy_tag = models.Tag.objects.create(name="blue", color="blue")
    models.AssetTag.objects.create(tag=tag_red, asset=asset)
    models.AssetTag.objects.create(tag=tag_green, asset=asset)
    response = auth_client.get(f"/api/tags/?asset={asset.pk}")
    tags = response.data["results"]
    assert len(tags) == 2  # noqa: PLR2004
    assert {t["id"] for t in tags} == {tag_red.pk, tag_green.pk}


def test_get_asset_vulnerabilities_obsolete(auth_client, asset_vulnerabilities):
    """Test old /api/assets/<n>/vulnerabilities way to get vulns for asset."""
    asset = asset_vulnerabilities[0]
    response = auth_client.get(f"/api/assets/{asset.id}/vulnerabilities/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_asset_vulnerabilities_new(auth_client, asset_vulnerabilities):
    """Test new /api/vulnerabilities/?asset=<n> way to get vulns for asset."""
    (asset, vulnerability_red, vulnerability_green) = asset_vulnerabilities
    response = auth_client.get(f"/api/vulnerabilities/?asset={asset.id}")
    vulnerabilities = response.data["results"]
    assert len(vulnerabilities) == 2  # noqa: PLR2004
    assert {v["id"] for v in vulnerabilities} == {
        vulnerability_red.id,
        vulnerability_green.id,
    }


def test_get_asset_asset_vulnerabilities_obsolete(auth_client, asset_vulnerabilities):
    """Test old /api/assets/<n>/assetvulnerabilities route for asset_vulns."""
    asset = asset_vulnerabilities[0]
    response = auth_client.get(f"/api/assets/{asset.id}/assetvulnerabilities/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_asset_asset_vulnerabilities_new(auth_client, asset_vulnerabilities):
    """Test new /api/assetvulnerabilities/?asset=<n> route for asset_vulns."""
    (asset, vulnerability_red, vulnerability_green) = asset_vulnerabilities
    response = auth_client.get(f"/api/assetvulnerabilities/?asset={asset.id}")
    asset_vulnerabilities = response.data["results"]
    assert len(asset_vulnerabilities) == 2  # noqa: PLR2004
    assert {av["vulnerability"]["id"] for av in asset_vulnerabilities} == {
        vulnerability_red.id,
        vulnerability_green.id,
    }
    assert all(av["asset_id"] == asset.id for av in asset_vulnerabilities)


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
    # assert response.status_code == status.HTTP_404_NOT_FOUND
    networks = response.data["results"]
    assert len(networks) == 1
    assert networks[0]["id"] == network.pk


def test_get_asset_network_new_api(admin_client):
    """Ensure we can determine which assets belong in network."""
    asset = models.Asset.objects.create(ip_address="10.0.0.1")
    dummy_asset_out_of_network = models.Asset.objects.create(ip_address="10.0.1.1")
    network_blue = models.Network.objects.create(name="blue")
    network_blue.cidr = ["10.0.0.0/24"]
    network_red = models.Network.objects.create(name="red")
    network_red.cidr = ["10.0.0.0/31"]
    dummy_network = models.Network.objects.create(name="dummy_1")
    dummy_network.cidr = ["10.0.1.0/24"]
    response = admin_client.get(f"/api/networks/?asset={asset.pk}")
    networks = response.data["results"]
    assert len(networks) == 2  # noqa: PLR2004
    assert {n["id"] for n in networks} == {network_blue.pk, network_red.pk}
