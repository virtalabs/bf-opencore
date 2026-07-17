"""Asset is the core model for tracking all internal systems."""

import datetime
import logging
import typing

import netaddr
from django.db import models
from simple_history import models as simple_history

from blueflow.models import (
    cpe,
    group,
    ports_protocol,
    tag,
    usage,
)

from . import system, util

logger = logging.getLogger(__name__)


class Asset(system.System):
    """Asset represents any system internal to the owned network.

    Asset instances are intended to be queried and managed by its parent:
    ex:
    s = System.objects.first()
    asset = getattr(s, "asset", None)

    Inherits ``created`` and ``modified`` from ``TimeStampedModel``. ``modified``
    is the sync anchor used by the Viper webhook — it updates on every save,
    including upserts. ``last_pinged`` is reserved for the network
    layer and is only set when the asset is observed on the wire (ping,
    fingerprint), so it is not safe to use as a "recently changed" filter.
    """

    UNKNOWN_OUI_MANUFACTURER: str = ""

    name = models.CharField(
        max_length=126,
        blank=True,
        null=False,
        default="",
    )
    # we want nullable for uniqueness
    hostname = models.CharField(  # noqa: DJ001
        max_length=256,
        blank=False,
        null=True,
        unique=True,
    )
    oui_manufacturer = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        verbose_name="NIC vendor",
        default="",
    )
    manufacturer = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        default="",
    )
    model = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        default="",
    )
    serial_number = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        default="",
    )
    udi = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        verbose_name="UDI",
        default="",
    )
    tag_number = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        default="",
    )
    category = models.CharField(
        max_length=256,
        blank=True,
        null=False,
        default="",
    )
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
        null=False,
        default=util.default_timestamp,
    )
    last_pinged = models.DateTimeField(
        null=False,
        default=util.default_timestamp,
    )
    external_keys = models.JSONField(
        blank=True,
        null=True,
    )
    groups = models.ManyToManyField(
        group.Group,
        through=group.AssetGroup,
    )
    tags = models.ManyToManyField(
        tag.Tag,
        through=tag.AssetTag,
    )
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
        """Build this asset's CPE 2.3 string from manufacturer / model.

        Delegates to :func:`blueflow.models.cpe.build_cpe` so the CPE format is
        defined in one place; most slots are still stubbed pending real data.
        """
        return cpe.build_cpe(self)

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
        return f"{self.id}:{self.hostname}:{self.ip_address}"

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

    def add_interface(self, **kwargs):
        interface = super().add_interface(**kwargs)
        if not self.interface.mac_address:
            return interface
        mac = self.interface.mac_address
        try:
            reg = mac.oui.registration()
            self.oui_manufacturer = reg.org.strip()
        except netaddr.core.AddrFormatError:
            logger.warning("Bad MAC address on asset %s", self)
            self.oui_manufacturer = self.UNKNOWN_OUI_MANUFACTURER
        except netaddr.core.NotRegisteredError:
            logger.info(
                "MAC address %s of asset %s lacks NIC vendor",
                mac,
                self,
            )
            self.oui_manufacturer = self.UNKNOWN_OUI_MANUFACTURER
        except AttributeError:
            logger.debug(
                "NIC vendor registry lacks org detail for MAC address %s",
                mac,
            )
            self.oui_manufacturer = self.UNKNOWN_OUI_MANUFACTURER
        return interface

    def update_usage(self, timestamp: datetime.datetime) -> None:
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
