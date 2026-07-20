import netfields
from django.db import models
from django_extensions.db import models as django_extensions


class NetworkInterface(django_extensions.TimeStampedModel):
    system = models.OneToOneField(
        "System", related_name="interface", on_delete=models.CASCADE
    )
    mac_address = netfields.MACAddressField(
        null=True,
        unique=True,
        verbose_name="MAC address",
    )
    ipv4 = netfields.InetAddressField(
        store_prefix_length=False,
        null=True,
        verbose_name="IP address",
        max_length=12,
    )
    ipv6 = netfields.InetAddressField(
        store_prefix_length=False,
        null=True,
        verbose_name="IP address",
        max_length=36,
    )

    @property
    def ip_address(self) -> str:
        """Provide the ipv4 or ipv6 address.

        Empty string is the fallback when both other options are falsey.
        """
        if self.ipv4:
            return str(self.ipv4)
        if self.ipv6:
            return str(self.ipv6)
        return ""
