from django.db import models

from . import asset, constants


class PortProtocol(models.Model):
    """A mapping of Ports <-> protocol.

    Currently a port can only have one protocol as described by the textchoices.
    """

    class Protocols(models.TextChoices):
        tcp = "TCP"
        udp = "UDP"

    # https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers
    port = models.IntegerField(
        min_value=constants.PORT_MIN, max_value=constants.PORT_MAX, unique=True
    )
    protocol = models.CharField(
        choices=Protocols, default=Protocols.tcp, blank=False, null=False
    )

    def __str__(self) -> str:
        return f"{self.port}: {self.protocol}"


class AssetPortProtocol(models.Model):
    """Maps an asset to any number of port_protocols."""

    asset = models.ForeignKey(
        asset.Asset, related_name="port_protocols", on_delete=models.CASCADE
    )
    port_protocol = models.ForeignKey(PortProtocol, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.asset}: {self.port_protocol}"
