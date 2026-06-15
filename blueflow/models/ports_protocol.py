import typing

from django.core import validators
from django.db import models

from . import constants


class PortProtocol(models.Model):
    """A mapping of Ports <-> protocol.

    Currently a port can only have one protocol as described by the textchoices.
    """

    class Protocols(models.TextChoices):
        TCP = "tcp"
        UDP = "udp"

    # https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers
    port = models.PositiveSmallIntegerField(
        validators=[
            validators.MinValueValidator(constants.PORT_MIN),
            validators.MaxValueValidator(constants.PORT_MAX),
        ]
    )
    protocol = models.CharField(
        choices=Protocols.choices, default=Protocols.TCP, blank=False, null=False
    )

    class Meta:
        constraints: typing.ClassVar = [
            models.UniqueConstraint(
                fields=("port", "protocol"), name="unique_port_protocol"
            )
        ]

    def __str__(self) -> str:
        return f"{self.port}: {self.protocol}"


class AssetPortProtocol(models.Model):
    """Maps an asset to any number of port_protocols."""

    asset = models.ForeignKey(
        "blueflow.Asset", related_name="port_protocols", on_delete=models.CASCADE
    )
    port_protocol = models.ForeignKey(PortProtocol, on_delete=models.CASCADE)

    def __str__(self) -> str:
        return f"{self.asset}: {self.port_protocol}"
