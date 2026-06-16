"""Blueflow Asset model / schema.

Note: AssetManager has been moved to its own file asset_manager.py.
"""

import datetime
import logging
import typing

import netaddr
import netfields
from django.db import models
from django_extensions.db import models as django_extensions
from simple_history import models as simple_history

from blueflow.models import (
    group,
    ports_protocol,
    tag,
    usage,
)

logger = logging.getLogger(__name__)


def validate_tcp_port_range(_: list[int]) -> None:
    """Retained as an import target for historical migrations only."""


class Asset(django_extensions.TimeStampedModel):
    """Holds our Assets.

    Inherits ``created`` and ``modified`` from ``TimeStampedModel``. ``modified``
    is the sync anchor used by the Viper webhook — it updates on every save,
    including TapirXL upserts. ``last_pinged`` is reserved for the network
    layer and is only set when the asset is observed on the wire (ping,
    fingerprint), so it is not safe to use as a "recently changed" filter.
    """

    UNKNOWN_CPE_VALUE: str = "*"

    name = models.CharField(max_length=126, blank=True, null=False, default="")
    hostname = models.CharField(
        max_length=256, blank=True, null=False, unique=True, default=""
    )
    ip_address = netfields.InetAddressField(
        store_prefix_length=False,
        null=True,
        verbose_name="IP address",
    )
    mac_address = netfields.MACAddressField(
        null=True,
        unique=True,
        verbose_name="MAC address",
    )
    oui_manufacturer = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        verbose_name="NIC vendor",
        default="",
    )
    manufacturer = models.CharField(max_length=256, blank=True, null=False, default="")
    model = models.CharField(max_length=256, blank=True, null=False, default="")
    serial_number = models.CharField(max_length=256, blank=True, null=False, default="")
    udi = models.CharField(
        max_length=256, blank=True, null=False, verbose_name="UDI", default=""
    )
    tag_number = models.CharField(max_length=256, blank=True, null=False, default="")
    category = models.CharField(max_length=256, blank=True, null=False, default="")

    owner = models.CharField(max_length=256, blank=True, null=False, default="")
    os = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        verbose_name="Operating System",
        default="",
    )
    app_sw_version = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        verbose_name="Application software version",
        default="",
    )
    last_scanned = models.DateTimeField(
        null=False, default=datetime.datetime.now(datetime.UTC)
    )
    last_pinged = models.DateTimeField(
        null=False, default=datetime.datetime.now(datetime.UTC)
    )
    groups = models.ManyToManyField(group.Group, through=group.AssetGroup)
    tags = models.ManyToManyField(tag.Tag, through=tag.AssetTag)
    history = simple_history.HistoricalRecords()

    class Meta:
        constraints: typing.ClassVar = (
            models.CheckConstraint(
                condition=models.Q(hostname__isnull=True) | ~models.Q(hostname=""),
                name="asset_hostname_not_empty_when_set",
            ),
        )

    @property
    def cpe(self) -> str:
        """Builds the cpe string from the asset dataclass.

        Cached after first build. Lots of this data is mocked atm, we'll need
        to get specifics from Cassidy for the demo.
        """
        cpe: str = ":".join(
            [
                "cpe",  # always the same
                "2.3",  # version
                "h",  # 'part' # h for now but: https://en.wikipedia.org/wiki/Common_Platform_Enumeration#part
                str(self.manufacturer or self.UNKNOWN_CPE_VALUE),  # vendor
                str(
                    self.model or self.UNKNOWN_CPE_VALUE
                ),  # product # do we want something different ?
                "-",
                # version of product?
                self.UNKNOWN_CPE_VALUE,
                # point release / minor versions
                self.UNKNOWN_CPE_VALUE,
                # any additional information beyond version for id
                self.UNKNOWN_CPE_VALUE,
                # lang is empty for now
                self.UNKNOWN_CPE_VALUE,
                # en-US -- https://datatracker.ietf.org/doc/html/rfc5646
                # "edition" i.e. MS desktop vs MS Server etc
                self.UNKNOWN_CPE_VALUE,
                # 'target' wiki ex: `windows_2003` & `ipod_touch`
                self.UNKNOWN_CPE_VALUE,
                # 'target_hw', but really the cpu architecture type
                self.UNKNOWN_CPE_VALUE,
            ]
        )
        return cpe

    @property
    def services(self) -> dict[int, list[str]]:
        """A list of services associated with this asset.

        Assumes you'd prefetched as needed
        """
        services = {}
        for pp in self.port_protocols.all():
            port = int(pp.port_protocol.port)
            protocol = str(pp.port_protocol.protocol)
            _list: list[str] = services.setdefault(port, [])
            _list.append(protocol)
            services[port] = _list
        return services

    def __str__(self) -> str:
        return f"{self.id}:{self.display_name}:{self.ip_address}"

    def save(self, *args: typing.Any, **kwargs: typing.Any):
        """Intercept save, automatically populating some fields."""
        if self.mac_address:
            try:
                eui = netaddr.EUI(self.mac_address)
                reg = eui.oui.registration()
                self.oui_manufacturer = reg.org.strip()
            except netaddr.core.AddrFormatError:
                logger.warning("Bad MAC address on asset %s", self)
                self.oui_manufacturer = None
            except netaddr.core.NotRegisteredError:
                logger.info(
                    "MAC address %s of asset %s lacks NIC vendor",
                    self.mac_address,
                    self,
                )
                self.oui_manufacturer = None
            except AttributeError:
                logger.debug(
                    "NIC vendor registry lacks org detail for MAC address %s",
                    self.mac_address,
                )
                self.oui_manufacturer = None

        super().save(*args, **kwargs)

    def add_service(self, port: int, protocol: str) -> bool:
        """Idempotently link this asset to a ``(port, protocol)`` observation.

        The shared ``PortProtocol`` lookup row is created on first use; the
        per-asset through row is created on first reference. Returns True if a
        new link was created, False if it already existed.
        """
        port_protocol, _ = ports_protocol.PortProtocol.objects.get_or_create(
            port=port, protocol=protocol
        )
        _, created = ports_protocol.AssetPortProtocol.objects.get_or_create(
            asset=self, port_protocol=port_protocol
        )
        return created

    def update_usage(self, timestamp: datetime.datetime):
        """Record a usage observation for this asset at the given timestamp.

        Looks up (or creates) the Usage row for this asset on
        timestamp.weekday(), then increments the matching hour_NN column —
        unless an observation has already been counted for the same
        Usage.USAGE_WINDOW_MINUTES window, in which case this is a no-op.
        """
        window_start = usage.Usage.floor_to_window(timestamp)
        u, _ = usage.Usage.objects.get_or_create(
            asset=self,
            day_of_week=timestamp.weekday(),
        )
        if u.last_window_started_at == window_start:
            return
        hour_field = f"hour_{timestamp.hour:02d}"
        setattr(u, hour_field, getattr(u, hour_field) + 1)
        u.last_window_started_at = window_start
        u.save()

    def todict(self) -> dict[str, str]:
        """Return concrete fields as a dictionary for diffing in update_or_create."""
        return {f.name: str(getattr(self, f.attname, None)) for f in self._meta.fields}
