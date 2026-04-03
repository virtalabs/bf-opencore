"""Portscan connector tests."""

# These pylint warnings are endemic to pytest
# pylint: disable=redefined-outer-name,unused-argument

# BlueFlow models do have 'objects' member, but it's being lazy loaded
# pylint: disable=no-member

import unittest.mock

import django.core.management
import pytest

import blueflow
from blueflow.models import Asset

sample_stdout = b"""
Starting Nmap 7.70 ( https://nmap.org ) at 2019-06-11 08:56 PDT
Initiating SYN Stealth Scan at 08:56
Scanning localhost (127.0.0.1) [1000 ports]
Discovered open port 1234/tcp on 127.0.0.1
Discovered open port 5678/tcp on 127.0.0.1
Completed SYN Stealth Scan at 08:56, 3.16s elapsed (1000 total ports)
Nmap scan report for localhost (127.0.0.1)
Host is up (0.000012s latency).
Other addresses for localhost (not scanned): ::1
Not shown: 500 filtered ports, 499 closed ports
PORT     STATE SERVICE
1234/tcp open  baz
5678/tcp open  quux

Read data files from: /usr/local/bin/../share/nmap
Nmap done: 1 IP address (1 host up) scanned in 3.21 seconds
           Raw packets sent: 1502 (66.088KB) | Rcvd: 2003 (86.132KB)
""".lstrip()


@pytest.fixture
def setup_db(db):
    """Create connector objects."""
    raise NotImplementedError("Connectors have been removed")
    # ConnectorTask objects are linked to Connector objects with a foreign key
    # relationship.  We need those objects to be available.
    django.core.management.call_command("create_connectors")

    # First enable Connector that's disabled by default
    connector = Connector.objects.get(id="portscan")
    connector.enabled = True
    connector.save()


@unittest.mock.patch("sh.sudo", create=True)
def test_portscan_basic(mock_sudo, setup_db):
    """Sudo nmap plumbing works."""
    raise NotImplementedError("Connectors have been removed")
    mock_sudo.return_value.stdout = sample_stdout
    mock_sudo.return_value.stderr = b""
    mock_sudo.return_value.exit_code = 0

    kwargs = {"hostname": "localhost"}
    status = blueflow.portscan.main.apply(kwargs=kwargs)
    assert status.result is not None

    ct = ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert ct.stdout.rstrip() == sample_stdout.decode("utf-8").rstrip()
    assert ct.stderr == ""


@unittest.mock.patch("sh.sudo", create=True)
def test_portscan_scan_object(mock_sudo, setup_db):
    """Portscan connector creates a Scan object."""
    raise NotImplementedError("Connectors have been removed")
    asset = Asset.objects.create(ip_address="127.0.0.1")
    mock_sudo.return_value.stdout = sample_stdout
    mock_sudo.return_value.stderr = b""
    mock_sudo.return_value.exit_code = 0

    kwargs = {"hostname": "localhost"}
    status = blueflow.portscan.main.apply(kwargs=kwargs)
    assert status.result is not None

    ct = ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert ct.stdout.rstrip() == sample_stdout.decode("utf-8").rstrip()
    assert ct.stderr == ""

    asset.refresh_from_db()
    assert set(asset.open_ports_tcp) == {1234, 5678}
    assert asset.vulnerabilities.count() == 0

    scans = asset.scan_qset()
    assert scans.count() == 1
    scan = scans.first()
    assert scan.provenance.startswith("Portscan")
    assert scan.connector_task == ct
    assert scan.num_vulnerabilities == 0
    assert scan.num_plugins == 0
