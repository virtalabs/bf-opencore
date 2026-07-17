import ipaddress

import netaddr
from model_bakery import baker

from . import System, asset, interface


def test_network_interface_system_creation() -> None:
    system = baker.make("System")
    ipv4 = ipaddress.ip_address("127.0.0.1")
    ipv6 = ipaddress.ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    mac = netaddr.EUI("00:00:0A:BB:28:FC")
    network_interface = interface.NetworkInterface.objects.create(
        system=system, ipv4=ipv4, ipv6=ipv6, mac_address=mac
    )
    first_system = System.objects.first()
    assert first_system.id is network_interface.system.id


def test_network_interface_asset_creation() -> None:
    asset_instance = baker.make("Asset")
    ipv4 = ipaddress.ip_address("127.0.0.1")
    ipv6 = ipaddress.ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    mac = netaddr.EUI("00:00:0A:BB:28:FC")
    network_interface = interface.NetworkInterface.objects.create(
        system=asset_instance, ipv4=ipv4, ipv6=ipv6, mac_address=mac
    )
    first_asset = asset.Asset.objects.first()
    assert first_asset.id is network_interface.system.id
