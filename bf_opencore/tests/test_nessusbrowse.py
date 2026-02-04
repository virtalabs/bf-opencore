"""Test our API for browsing Nessus scans.

Since the nessusbrowse API passes requests on to the Nessus REST API, we
need the Nessus server to be running.  We use environment variables to
determine if we can connect or not.

Parameters for connecting to Nessus on Beast as of 2017-11-21:

  export BLUEFLOW_NESSUS_URL=https://192.168.218.102:8834
  export BLUEFLOW_NESSUS_ACCESS_KEY=0d982352d07a3a896d783caa77b947f8 \
                                    6defb0be6de918e6bbb06461a634e176
  export BLUEFLOW_NESSUS_SECRET_KEY=4b6f6966156e0b4ee3fb9913d2f58c5f \
                                    5e0437e1141cd71c8dc1c084e76283e7
"""

import warnings
import os

import pytest
import requests

import blueflow.models as bf_mod
from connectors.management.commands.create_connectors import create_connectors
from api.views import nessusbrowse


warnings.filterwarnings(
    action="ignore",
    message=".*Unverified HTTPS request is being made.*",
    category=requests.packages.urllib3.exceptions.InsecureRequestWarning)


NESSUS_CONNECTOR_ID = nessusbrowse.NessusConnection.NESSUS_CONNECTOR_ID
NESSUS_URL = os.environ.get('BLUEFLOW_NESSUS_URL')
NESSUS_AKEY = os.environ.get('BLUEFLOW_NESSUS_ACCESS_KEY', '123abc')
NESSUS_SKEY = os.environ.get('BLUEFLOW_NESSUS_SECRET_KEY', '456def')
NESSUS_INSECURE = True

NESSUS_GOOD_SCAN_ID = 432
NESSUS_BAD_SCAN_ID = 'spam'
NESSUS_GOOD_HISTORY_ID = 432


@pytest.fixture
def nessus_connector():
    """Nessus connector with proper settings."""
    create_connectors()
    nc = bf_mod.Connector.objects.get(id=NESSUS_CONNECTOR_ID)
    nc.settings['url'] = NESSUS_URL
    nc.settings['access_key'] = NESSUS_AKEY
    nc.settings['secret_key'] = NESSUS_SKEY
    nc.settings['insecure'] = NESSUS_INSECURE
    nc.save()
    return nc


need_live_nessus = pytest.mark.skipif(not NESSUS_URL,
                                      reason='need live Nessus server')


def test_settings_no_connector(auth_client):
    """When connectors haven't been initialized, raise exception."""
    with pytest.raises(bf_mod.Connector.DoesNotExist):
        dummy = auth_client.get('/api/nessusbrowse/?action=scans')


@need_live_nessus
def test_settings_no_query(auth_client, nessus_connector):
    """We need a query parameter in order to get anything back."""
    response = auth_client.get('/api/nessusbrowse/')
    assert response.status_code == 400


def test_settings_no_url(auth_client, nessus_connector):
    """When Nessus connector isn't configured properly, raise exception."""
    nessus_connector.settings['url'] = ''
    nessus_connector.save()
    scans = auth_client.get('/api/nessusbrowse/?action=scans')
    assert scans.status_code == 400
    assert 'nessus_response' not in scans.json()
    assert 'detail' in scans.json()


def test_settings_no_keys(auth_client, nessus_connector):
    """When Nessus connector isn't configured properly, raise exception."""
    nessus_connector.settings['access_key'] = ''
    nessus_connector.save()
    scans = auth_client.get('/api/nessusbrowse/?action=scans')
    assert scans.status_code == 400
    assert 'nessus_response' not in scans.json()
    assert 'detail' in scans.json()


def test_bad_url(auth_client, nessus_connector):
    """With a bad URL, we'll get a HTTP error."""
    nessus_connector.settings['url'] = 'http://this.is.a.bad.url/'
    nessus_connector.save()
    with pytest.raises(requests.exceptions.ConnectionError):
        dummy = auth_client.get('/api/nessusbrowse/?action=scans')


@need_live_nessus
def test_get_scans(auth_client, nessus_connector):
    """Get list of scans."""
    scans = auth_client.get('/api/nessusbrowse/?action=scans')
    # assert 'nessus_response' in scans.json()
    # assert 'scans' in scans.json()['nessus_response']
    first_scan = scans.json()['nessus_response']['scans'][0]
    keys = {'id', 'name', 'uuid', 'status',
            'creation_date', 'last_modification_date'}
    assert keys.issubset(first_scan.keys())


@need_live_nessus
def test_get_scan_history(auth_client, nessus_connector):
    """History list for one scan."""
    history = auth_client.get('/api/nessusbrowse/?action=history&scan_id={}'
                              ''.format(NESSUS_GOOD_SCAN_ID))
    # assert 'nessus_response' in history.json()
    # assert 'history' in history.json()['nessus_response']
    first_history = history.json()['nessus_response']['history'][0]
    keys = {'history_id', 'uuid', 'status',
            'creation_date', 'last_modification_date'}
    assert keys.issubset(first_history.keys())


@need_live_nessus
def test_get_scan_history_bad_scan_id(auth_client, nessus_connector):
    """Bad scan ID (not integer) should give a ValidationError."""
    history = auth_client.get('/api/nessusbrowse/?action=history&scan_id={}'
                              ''.format(NESSUS_BAD_SCAN_ID))
    # This would raise a validation error... which looks kind of like this
    assert isinstance(history.json(), list)
    assert len(history.json()) == 1
    assert history.status_code == 400


@need_live_nessus
def test_get_scan_history_no_scan_id(auth_client, nessus_connector):
    """Nonexistent scan ID should give a ValidationError."""
    history = auth_client.get('/api/nessusbrowse/?action=history')
    # This would raise a validation error... which looks kind of like this
    assert isinstance(history.json(), list)
    assert len(history.json()) == 1
    assert history.status_code == 400


@pytest.mark.xfail(reason="Not yet implemented")
@need_live_nessus
def test_get_scan_detail(auth_client, nessus_connector):
    """History list for one scan."""
    details = auth_client.get('/api/nessusbrowse/'
                              '?action=details&scan_id={}&history_id={}'
                              ''.format(NESSUS_GOOD_SCAN_ID,
                                        NESSUS_GOOD_HISTORY_ID))
    # TODO: find out what we really want from details...
    assert 'nessus_response' in details.json()
    assert 'details' in details.json()['nessus_response']
