import ipaddress

import netaddr
from model_bakery import baker

from . import System, interface


def test_network_interface_ipv4() -> None:
    interface.NetworkInterface.objects.create(ipv4=ipaddress.ip_address("127.0.0.1"))


def test_network_interface_ipv6() -> None:
    ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
    interface.NetworkInterface.objects.create(ipv6=ipaddress.ip_address(ipv6))


def test_network_interface_mac_address() -> None:
    mac = "00:00:0A:BB:28:FC"
    interface.NetworkInterface.objects.create(mac_address=netaddr.EUI(mac))


def test_network_interface_system_fk() -> None:
    system = baker.make("System")
    ipv4 = ipaddress.ip_address("127.0.0.1")
    ipv6 = ipaddress.ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
    mac = netaddr.EUI("00:00:0A:BB:28:FC")
    network_interface = interface.NetworkInterface.objects.create(
        system=system, ipv4=ipv4, ipv6=ipv6, mac_address=mac
    )
    first_system = System.objects.first()
    assert first_system is network_interface.system
