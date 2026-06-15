import typing

from django.core import validators
from django.db import models
from django.db.models import Q

from . import constants


class PortProtocol(models.Model):
    """A mapping of Ports <-> protocol.

    ``protocol`` is a free-form string (e.g. ``tcp``, ``udp``, ``sctp``,
    ``udplite``); callers are responsible for picking sensible values.
    """

    # https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers
    port = models.PositiveSmallIntegerField(
        validators=[
            validators.MinValueValidator(constants.PORT_MIN),
            validators.MaxValueValidator(constants.PORT_MAX),
        ]
    )
    protocol = models.CharField(max_length=constants.PROTOCOL_MAX_LENGTH)

    class Meta:
        constraints: typing.ClassVar = [
            models.UniqueConstraint(
                fields=("port", "protocol"), name="unique_port_protocol"
            ),
            models.CheckConstraint(
                condition=~Q(protocol=""),
                name="port_protocol_protocol_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.port}: {self.protocol}"


class AssetPortProtocol(models.Model):
    """Maps an asset to any number of port_protocols."""

    asset = models.ForeignKey(
        "blueflow.Asset", related_name="port_protocols", on_delete=models.CASCADE
    )
    port_protocol = models.ForeignKey(PortProtocol, on_delete=models.CASCADE)

    class Meta:
        constraints: typing.ClassVar = [
            models.UniqueConstraint(
                fields=("asset", "port_protocol"),
                name="unique_asset_port_protocol",
            )
        ]

    def __str__(self) -> str:
        return f"{self.asset}: {self.port_protocol}"
