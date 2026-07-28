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


class SystemRequest(models.Model):
    """Maps an asset to any number of requests."""

    sender = models.ForeignKey(
        "blueflow.System", related_name="request_senders", on_delete=models.CASCADE
    )
    receiver = models.ForeignKey(
        "blueflow.System",
        null=True,
        related_name="request_receivers",
        on_delete=models.CASCADE,
    )
    request = models.ForeignKey(
        Request, related_name="system_requests", on_delete=models.CASCADE
    )

    class Meta:
        constraints: typing.ClassVar = [
            models.UniqueConstraint(
                fields=("sender", "receiver", "request"),
                name="unique_sender_receiver_request",
            )
        ]

    def __str__(self) -> str:
        return f"{self.sender}: {self.request}"
