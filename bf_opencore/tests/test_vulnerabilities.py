"""Vulnerabilities tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import pytest
from django.utils import timezone
from bf_opencore import models


def test_get_vulnerable_asset_obsolete(auth_client):
    """Test a route that's now obsolete."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    dummy_asset_obj = models.Asset.objects.create(hostname="spam.com")
    # The dummy_vulnerability is here only to artificially increment the
    # pk/id in order to verify proper behaviour.
    dummy_vulnerability = models.Vulnerability.objects.create(name="dummy")
    vulnerability = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(
        vulnerability=vulnerability, asset=asset_obj
    )
    response = auth_client.get(f"/api/vulnerabilities/{vulnerability.id}/assets/")
    assert response.status_code == 404


def test_get_vulnerable_asset_new(auth_client):
    """Test route /api/assets/?vulnerability=<id>."""
    asset_obj = models.Asset.objects.create(hostname="foo.com")
    dummy_asset_obj = models.Asset.objects.create(hostname="spam.com")
    # Increment the pk/id in order to verify behaviour commented on above.
    dummy_vulnerability = models.Vulnerability.objects.create(name="dummy")
    vulnerability = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(
        vulnerability=vulnerability, asset=asset_obj
    )
    response = auth_client.get(f"/api/assets/?vulnerability={vulnerability.id}")
    assets = response.data["results"]
    assert len(assets) == 1
    assert assets[0]["id"] == asset_obj.id


def test_get_vulnerable_assets(auth_client):
    """Get more than one vulnerable asset."""
    asset_1 = models.Asset.objects.create(hostname="one.foo.com")
    asset_2 = models.Asset.objects.create(hostname="two.foo.com")
    vuln = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(vulnerability=vuln, asset=asset_1)
    models.AssetVulnerability.objects.create(vulnerability=vuln, asset=asset_2)

    response = auth_client.get(f"/api/assets/?vulnerability={vuln.id}")
    assets = response.data["results"]
    assert len(assets) == 2
    assert {a["id"] for a in assets} == set([asset_1.id, asset_2.id])


def test_get_vulnerable_assets_ignored(auth_client):
    """Get all assets (also ignored) unless explicitly filtered out."""
    asset_1 = models.Asset.objects.create(hostname="one.foo.com")
    asset_2 = models.Asset.objects.create(hostname="two.foo.com")
    vuln = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(vulnerability=vuln, asset=asset_1)
    models.AssetVulnerability.objects.create(
        vulnerability=vuln, asset=asset_2, date_ignored=timezone.now()
    )
    response = auth_client.get(f"/api/assets/?vulnerability={vuln.id}")
    assets = response.data["results"]
    assert len(assets) == 2
    assert {a["id"] for a in assets} == set([asset_1.id, asset_2.id])


def test_get_vulnerable_assets_hide_ignored(auth_client):
    """Don't get ignored assets if filtered out."""
    asset_1 = models.Asset.objects.create(hostname="one.foo.com")
    asset_2 = models.Asset.objects.create(hostname="two.foo.com")
    vuln = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(vulnerability=vuln, asset=asset_1)
    models.AssetVulnerability.objects.create(
        vulnerability=vuln, asset=asset_2, date_ignored=timezone.now()
    )
    response = auth_client.get(
        "/api/assets/"
        f"?vulnerability={vuln.id}"
        "&asset_vulnerabilities__date_ignored__isnull=true"
    )
    assets = response.data["results"]
    assert len(assets) == 1
    assert {a["id"] for a in assets} == set([asset_1.id])


def test_get_vulnerable_assets_remediated(auth_client):
    """Get all assets (also remediated) unless explicitly filtered out."""
    asset_1 = models.Asset.objects.create(hostname="one.foo.com")
    asset_2 = models.Asset.objects.create(hostname="two.foo.com")
    vuln = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(vulnerability=vuln, asset=asset_1)
    models.AssetVulnerability.objects.create(
        vulnerability=vuln, asset=asset_2, date_remediated=timezone.now()
    )
    response = auth_client.get(f"/api/assets/?vulnerability={vuln.id}")
    assets = response.data["results"]
    assert len(assets) == 2
    assert {a["id"] for a in assets} == set([asset_1.id, asset_2.id])


def test_get_vulnerable_assets_hide_remediated(auth_client):
    """Don't get remediated assets if filtered out."""
    asset_1 = models.Asset.objects.create(hostname="one.foo.com")
    asset_2 = models.Asset.objects.create(hostname="two.foo.com")
    vuln = models.Vulnerability.objects.create(name="red")
    models.AssetVulnerability.objects.create(vulnerability=vuln, asset=asset_1)
    models.AssetVulnerability.objects.create(
        vulnerability=vuln, asset=asset_2, date_remediated=timezone.now()
    )
    response = auth_client.get(
        "/api/assets/"
        f"?vulnerability={vuln.id}"
        "&asset_vulnerabilities__date_remediated__isnull=true"
    )
    assets = response.data["results"]
    assert len(assets) == 1
    assert {a["id"] for a in assets} == set([asset_1.id])
