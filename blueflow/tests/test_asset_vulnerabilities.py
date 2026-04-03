"""Test asset vulnerability query strings."""

import json

from blueflow import models


def test_get_asset_vulnerabilities(auth_client, asset_vulnerabilities):
    """Test /api/assetvulnerabilities/?asset=<id> route for asset_vulns.

    This route should return the AssetVulnerabilities that are
    associated with the asset with the specified ID.
    """
    (asset, vulnerability_red, _vulnerability_green) = asset_vulnerabilities
    response = auth_client.get(f"/api/assetvulnerabilities/?asset={asset.id}")
    asset_vulnerabilities = response.data["results"]
    assert len(asset_vulnerabilities) == 2
    assert {av["vulnerability"]["id"] for av in asset_vulnerabilities} == {
        vulnerability_red.id,
        vulnerability_green.id,
    }
    assert all(av["asset_id"] == asset.id for av in asset_vulnerabilities)


def test_get_asset_vulnerabilities_model(auth_client, asset_vulnerabilities):
    """Test receiving AssetVulnerabilities for assets with a certain Model.

    URL route + query string is

        /api/assetvulnerabilities/?asset__model__iexact=<string>

    This route should return the AssetVulnerabilities that are
    associated with assets that have a model that start with <string>.
    """
    (asset, vulnerability_red, _vulnerability_green) = asset_vulnerabilities
    asset.model = "best-model"
    asset.save()
    a = models.Asset.objects.get(id=asset.id)
    assert a.model == asset.model
    assert a.model == "best-model"
    response = auth_client.get(
        "/api/assetvulnerabilities/?asset__model__iexact={}".format("best-model")
    )
    asset_vulnerabilities = response.data["results"]
    assert len(asset_vulnerabilities) == 2
    assert {av["vulnerability"]["id"] for av in asset_vulnerabilities} == {
        vulnerability_red.id,
        vulnerability_green.id,
    }
    assert all(av["asset_id"] == asset.id for av in asset_vulnerabilities)


def test_delete_asset_vulnerability(asset_edit_client, asset_vulnerabilities):
    """Test that we may remove a vulnerability from an asset.

    AKA delete an assetvulnerability.
    """
    (asset, vulnerability_red, _vulnerability_green) = asset_vulnerabilities
    av = models.AssetVulnerability.objects.get(
        asset=asset, vulnerability=vulnerability_red
    )
    response = asset_edit_client.delete(f"/api/assetvulnerabilities/{av.id}/")
    assert response.status_code == 204  # deleted


def test_update_asset_vulnerability(asset_edit_client, asset_vulnerabilities):
    """Test that we may mark a vulnerability as accepted/ignored for an asset.

    AKA update/patch an assetvulnerability.
    """
    (asset, vulnerability_red, _vulnerability_green) = asset_vulnerabilities
    av = models.AssetVulnerability.objects.get(
        asset=asset, vulnerability=vulnerability_red
    )
    assert av.date_remediated is None
    assert av.date_ignored is None
    response = asset_edit_client.patch(
        f"/api/assetvulnerabilities/{av.id}/",
        json.dumps({"ignore": "true"}),
        content_type="application/json",
    )
    assert response.status_code == 200  # deleted
    av = models.AssetVulnerability.objects.get(
        asset=asset, vulnerability=vulnerability_red
    )
    assert av.date_ignored is not None
