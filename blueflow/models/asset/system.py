import ipaddress

import netaddr
from django_extensions.db import models as django_extensions

from blueflow.models.interface import NetworkInterface


class System(django_extensions.TimeStampedModel):
    """System is the parent to all assets and asset like things.

    Its primary role is to provide a centralized query for both
    internal and external assets and asset like things.
    """

    def add_or_update_interface(
        self,
        *,
        mac_address: netaddr.EUI | str | None = None,
        ips: list[str] | None = None,
    ) -> NetworkInterface:
        kwargs = {}
        if mac_address is not None:
            mac = (
                netaddr.EUI(mac_address)
                if isinstance(mac_address, str)
                else mac_address
            )
            kwargs["mac_address"] = mac
        if ips is not None:
            for ip in ips:
                ip_address = ipaddress.ip_address(ip)
                match type(ip_address):
                    case ipaddress.IPv4Address:
                        kwargs["ipv4"] = ip_address
                    case ipaddress.IPv6Address:
                        kwargs["ipv6"] = ip_address
                    case _:
                        msg = "Unable to determine ip address type"
                        raise ValueError(msg)
        interface, _ = NetworkInterface.objects.update_or_create(
            system=self, defaults=kwargs
        )
        return interface

    @property
    def ip_address(self) -> str:
        return self.interface.ip_address

    @property
    def mac_address(self) -> str:
        return self.interface.mac_address
