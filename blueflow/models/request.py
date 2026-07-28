import typing

from django.core import validators
from django.db import models
from django.db.models import Q

from . import constants


class Request(models.Model):
    """Records a network request observation.

    ``protocol`` is a free-form string (e.g. ``tcp``, ``udp``, ``sctp``,
    ``udplite``); callers are responsible for picking sensible values.
    """

    class CastChoices(models.TextChoices):
        unicast = "unicast"
        multicast = "multicast"
        broadcast = "broadcast"

    # https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers
    port = models.PositiveSmallIntegerField(
        validators=[
            validators.MinValueValidator(constants.PORT_MIN),
            validators.MaxValueValidator(constants.PORT_MAX),
        ]
    )
    protocol = models.CharField(max_length=constants.PROTOCOL_MAX_LENGTH)
    cast_type = models.CharField(
        choices=CastChoices, null=False, default=CastChoices.unicast
    )
    service = models.CharField(null=False, blank=True, default="")
    response_seen = models.BooleanField(default=False, null=False)

    class Meta:
        constraints: typing.ClassVar = [
            models.UniqueConstraint(
                fields=("port", "protocol"), name="unique_request_port_protocol"
            ),
            models.CheckConstraint(
                condition=~Q(protocol=""),
                name="request_protocol_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.port}: {self.protocol}"


class AssetRequest(models.Model):
    """Maps an asset to any number of requests."""

    asset = models.ForeignKey(
        "blueflow.Asset", related_name="requests", on_delete=models.CASCADE
    )
    request = models.ForeignKey(Request, on_delete=models.CASCADE)
    sender = models.BooleanField(default=True, null=False)

    def __str__(self) -> str:
        return f"{self.asset}: {self.request}"
