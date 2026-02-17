"""Asset tests.

Uses built-in pytest-django text fixtures from
http://pytest-django.readthedocs.io/en/latest/helpers.html
"""

import pytest
import django.utils.timezone
from bf_opencore import models

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
          assert response.status_code == 404 (or 405)
    """
    asset = models.Asset.objects.create(hostname='foo.com')
    tag_red = models.Tag.objects.create(name='red', color='red')
    tag_green = models.Tag.objects.create(name='green', color='green')
    dummy_tag = models.Tag.objects.create(name='blue', color='blue')
    models.AssetTag.objects.create(tag=tag_red, asset=asset)
    models.AssetTag.objects.create(tag=tag_green, asset=asset)
    response = auth_client.get('/api/assets/{}/tags/'.format(asset.id))
    # assert response.status_code == 405
    # assert response.status_text == "Method Not Allowed"
    tags = response.data['results']
    assert len(tags) == 2
    assert {t['id'] for t in tags} == {tag_red.id, tag_green.id}


def test_get_asset_tags_new(auth_client):
    """Test new /api/tags/?asset=<n> way to get tags associated with asset."""
    asset = models.Asset.objects.create(hostname='foo.com')
    tag_red = models.Tag.objects.create(name='red', color='red')
    tag_green = models.Tag.objects.create(name='green', color='green')
    dummy_tag = models.Tag.objects.create(name='blue', color='blue')
    models.AssetTag.objects.create(tag=tag_red, asset=asset)
    models.AssetTag.objects.create(tag=tag_green, asset=asset)
    response = auth_client.get('/api/tags/?asset={}'.format(asset.id))
    tags = response.data['results']
    assert len(tags) == 2
    assert {t['id'] for t in tags} == {tag_red.id, tag_green.id}


################
# Vulnerabilities

@pytest.fixture
def asset_vulnerabilities(db):
    """Set up some database objects to test asset-vulnerability relations."""
    # db is a virtual arg to gain access to database
    asset = models.Asset.objects.create(hostname='foo.com')
    asset_2 = models.Asset.objects.create(hostname='bar.com')
    dummy_vulnerability = models.Vulnerability.objects.create(name='eggs')
    vulnerability_spam = models.Vulnerability.objects.create(name='spam')
    vulnerability_red = models.Vulnerability.objects.create(name='red')
    vulnerability_green = models.Vulnerability.objects.create(name='green')
    models.AssetVulnerability.objects.create(vulnerability=vulnerability_red,
                                             asset=asset)
    models.AssetVulnerability.objects.create(vulnerability=vulnerability_green,
                                             asset=asset)
    models.AssetVulnerability.objects.create(vulnerability=vulnerability_spam,
                                             asset=asset_2)
    return (asset, vulnerability_red, vulnerability_green)


# The following tests are "guilty" of this by necessity

def test_get_asset_vulnerabilities_obsolete(auth_client,
                                            asset_vulnerabilities):
    """Test old /api/assets/<n>/vulnerabilities way to get vulns for asset."""
    asset = asset_vulnerabilities[0]
    response = auth_client.get(
        '/api/assets/{}/vulnerabilities/'.format(asset.id))
    assert response.status_code == 404


def test_get_asset_vulnerabilities_new(auth_client,
                                       asset_vulnerabilities):
    """Test new /api/vulnerabilities/?asset=<n> way to get vulns for asset."""
    (asset, vulnerability_red, vulnerability_green) = asset_vulnerabilities
    response = auth_client.get(
        '/api/vulnerabilities/?asset={}'.format(asset.id))
    vulnerabilities = response.data['results']
    assert len(vulnerabilities) == 2
    assert ({v['id'] for v in vulnerabilities} ==
            {vulnerability_red.id, vulnerability_green.id})


def test_get_asset_asset_vulnerabilities_obsolete(auth_client,
                                                  asset_vulnerabilities):
    """Test old /api/assets/<n>/assetvulnerabilities route for asset_vulns."""
    asset = asset_vulnerabilities[0]
    response = auth_client.get(
        '/api/assets/{}/assetvulnerabilities/'.format(asset.id))
    assert response.status_code == 404


def test_get_asset_asset_vulnerabilities_new(auth_client,
                                             asset_vulnerabilities):
    """Test new /api/assetvulnerabilities/?asset=<n> route for asset_vulns."""
    (asset, vulnerability_red, vulnerability_green) = asset_vulnerabilities
    response = auth_client.get(
        '/api/assetvulnerabilities/?asset={}'.format(asset.id))
    asset_vulnerabilities = response.data['results']
    assert len(asset_vulnerabilities) == 2
    assert ({av['vulnerability']['id'] for av in asset_vulnerabilities} ==
            {vulnerability_red.id, vulnerability_green.id})
    assert all(av['asset_id'] == asset.id for av in asset_vulnerabilities)


################
# Scans

def test_get_asset_scans_obsolete(auth_client):
    """Test old /api/assets/<n>/scans way to get scans of asset.

    NOTE: will remove this route; then change assertion to
          assert response.status_code == 404 (or 405)
    """
    connector = models.Connector.objects.create(id='spam')
    c_task_1 = models.ConnectorTask.objects.create(connector=connector,
                                                   celery_task_id='1')
    c_task_2 = models.ConnectorTask.objects.create(connector=connector,
                                                   celery_task_id='2')
    c_task_3 = models.ConnectorTask.objects.create(connector=connector,
                                                   celery_task_id='3')
    asset = models.Asset.objects.create(hostname='foo.com')
    asset_dummy = models.Asset.objects.create(hostname='spam.com')
    aux_fields = {
        'date_scanned': django.utils.timezone.now(),
        'num_vulnerabilities': 0,
        'num_plugins': 0,
        }
    scan_red = models.Scan.objects.create(asset=asset,
                                          connector_task=c_task_1,
                                          **aux_fields)
    scan_green = models.Scan.objects.create(asset=asset,
                                            connector_task=c_task_2,
                                            **aux_fields)
    dummy_scan = models.Scan.objects.create(asset=asset_dummy,
                                            connector_task=c_task_1,
                                            **aux_fields)
    dummy_scan = models.Scan.objects.create(asset=asset_dummy,
                                            connector_task=c_task_3,
                                            **aux_fields)
    response = auth_client.get('/api/assets/{}/scans/'.format(asset.id))
    # assert response.status_code == 405
    # assert response.status_text == "Method Not Allowed"
    scans = response.data['results']
    assert len(scans) == 2
    assert {t['id'] for t in scans} == {scan_red.id, scan_green.id}


def test_get_asset_scans_new(auth_client):
    """Test new /api/scans/?asset=<n> way to get scans of asset."""
    connector = models.Connector.objects.create(id='spam')
    c_task_1 = models.ConnectorTask.objects.create(connector=connector,
                                                   celery_task_id='1')
    c_task_2 = models.ConnectorTask.objects.create(connector=connector,
                                                   celery_task_id='2')
    c_task_3 = models.ConnectorTask.objects.create(connector=connector,
                                                   celery_task_id='3')
    asset = models.Asset.objects.create(hostname='foo.com')
    asset_dummy = models.Asset.objects.create(hostname='spam.com')
    aux_fields = {
        'date_scanned': django.utils.timezone.now(),
        'num_vulnerabilities': 0,
        'num_plugins': 0,
        }
    scan_red = models.Scan.objects.create(asset=asset,
                                          connector_task=c_task_1,
                                          **aux_fields)
    scan_green = models.Scan.objects.create(asset=asset,
                                            connector_task=c_task_2,
                                            **aux_fields)
    dummy_scan = models.Scan.objects.create(asset=asset_dummy,
                                            connector_task=c_task_1,
                                            **aux_fields)
    dummy_scan = models.Scan.objects.create(asset=asset_dummy,
                                            connector_task=c_task_3,
                                            **aux_fields)
    response = auth_client.get('/api/scans/?asset={}'.format(asset.id))
    scans = response.data['results']
    assert len(scans) == 2
    assert {t['id'] for t in scans} == {scan_red.id, scan_green.id}
    # Sanity check (should get all scans.)
    response = auth_client.get('/api/scans/')
    scans = response.data['results']
    assert len(scans) == 4


################
# Networks

def test_get_asset_network_old_api(admin_client):
    """Ensure we can determine which assets belong in network.

    NOTE: will remove this route; then change assertion to
          assert response.status_code == 404
    """
    asset = models.Asset.objects.create(ip_address='10.0.0.1')
    network = models.Network.objects.create()
    network.cidr = ['10.0.0.0/24']
    response = admin_client.get('/api/assets/{}/networks/'.format(asset.id))
    # assert response.status_code == 404
    networks = response.data['results']
    assert len(networks) == 1
    assert networks[0]['id'] == network.id


def test_get_asset_network_new_api(admin_client):
    """Ensure we can determine which assets belong in network."""
    asset = models.Asset.objects.create(ip_address='10.0.0.1')
    dummy_asset_out_of_network = models.Asset.objects.create(
        ip_address='10.0.1.1')
    network_blue = models.Network.objects.create(name='blue')
    network_blue.cidr = ['10.0.0.0/24']
    network_red = models.Network.objects.create(name='red')
    network_red.cidr = ['10.0.0.0/31']
    dummy_network = models.Network.objects.create(name='dummy_1')
    dummy_network.cidr = ['10.0.1.0/24']
    response = admin_client.get('/api/networks/?asset={}'.format(asset.id))
    networks = response.data['results']
    assert len(networks) == 2
    assert {n['id'] for n in networks} == {network_blue.id, network_red.id}
