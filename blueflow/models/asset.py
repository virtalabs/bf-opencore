"""Blueflow Asset model / schema.

Note: AssetManager has been moved to its own file asset_manager.py.
"""

import logging
from collections import Counter
from functools import reduce
from operator import or_

import netaddr
import packaging.version
from django.apps import apps
from django.db import models
from django.db.models import Count, Max, Q
from django_extensions.db.models import TimeStampedModel
from netfields import InetAddressField, MACAddressField
from simple_history.models import HistoricalRecords

from blueflow.utils import NullUnlessChanged

from . import asset_custom_field, group, ports_protocol, tag, vulnerability

logger = logging.getLogger(__name__)


def validate_tcp_port_range(ports: list[int]) -> None:
    """Retained as an import target for historical migrations only."""


class Asset(TimeStampedModel):
    """Holds our Assets.

    Inherits ``created`` and ``modified`` from ``TimeStampedModel``. ``modified``
    is the sync anchor used by the Viper webhook — it updates on every save,
    including TapirXL upserts. ``last_pinged`` is reserved for the network
    layer and is only set when the asset is observed on the wire (ping,
    fingerprint), so it is not safe to use as a "recently changed" filter.
    """

    name = models.CharField(max_length=126, blank=True, null=False)
    hostname = models.TextField(blank=True, null=False, unique=True)
    ip_address = InetAddressField(
        store_prefix_length=False,
        blank=True,
        null=False,
        verbose_name="IP address",
    )
    mac_address = MACAddressField(
        blank=True,
        null=False,
        unique=True,
        verbose_name="MAC address",
    )
    oui_manufacturer = models.TextField(
        blank=True,
        null=False,
        verbose_name="NIC vendor",
    )
    manufacturer = models.TextField(blank=True, null=False)
    model = models.TextField(blank=True, null=False)
    serial_number = models.TextField(blank=True, null=False)
    udi = models.TextField(blank=True, null=False, verbose_name="UDI")
    tag_number = models.TextField(blank=True, null=False)
    category = models.TextField(blank=True, null=False)

    owner = models.TextField(blank=True, null=False)
    os = models.TextField(blank=True, null=False, verbose_name="Operating System")
    app_sw_version = models.TextField(
        blank=True,
        null=False,
        verbose_name="Application software version",
    )
    last_scanned = models.DateTimeField(blank=True, null=False)
    last_pinged = models.DateTimeField(blank=True, null=False)
    external_keys = models.JSONField(blank=True, null=False)
    groups = models.ManyToManyField(group.Group, through=group.AssetGroup)
    tags = models.ManyToManyField(tag.Tag, through=tag.AssetTag)
    vulnerabilities = models.ManyToManyField(
        vulnerability.Vulnerability,
        through=vulnerability.AssetVulnerability,
    )
    custom_fields = models.ManyToManyField(
        asset_custom_field.AssetCustomFieldName,
        through=asset_custom_field.AssetCustomField,
    )
    history = HistoricalRecords()

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=Q(hostname__isnull=True) | ~Q(hostname=""),
                name="asset_hostname_not_empty_when_set",
            ),
        )

    def save(self, *args, **kwargs):
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
            except AttributeError:  # no reg.org
                logger.debug(
                    "NIC vendor registry lacks org detail for MAC address %s",
                    self.mac_address,
                )
                self.oui_manufacturer = None

        super().save(*args, **kwargs)

    @property
    def cpe(self) -> str:
        """Builds the cpe string from the asset dataclass.

        Cached after first build. Lots of this data is mocked atm, we'll need
        to get specifics from Cassidy for the demo.
        """
        if _cpe := getattr(self, "_cpe", None):
            return _cpe
        unknown = "*"
        cpe = ":".join(
            [
                "cpe",  # always the same
                # TODO(taylorcochran): figure out what version cass wants
                "2.3",  # version
                "h",  # 'part' # h for now but: https://en.wikipedia.org/wiki/Common_Platform_Enumeration#part
                self.manufacturer or unknown,  # vendor
                self.model or unknown,  # product # do we want something different ?
                "-",
                unknown,  # version of product?
                unknown,  # point release / minor versions
                unknown,  # any additional information beyond version for id
                unknown,  # lang is empty for now
                # en-US -- https://datatracker.ietf.org/doc/html/rfc5646
                unknown,  # "edition" i.e. MS desktop vs MS Server etc
                unknown,  # 'target' wiki ex: `windows_2003` & `ipod_touch`
                unknown,  # 'target_hw', but really the cpu architecture type
            ]
        )
        self._cpe = cpe
        return self._cpe

    @property
    def last_updated(self):
        """Most recent update.  Utilize django-simple-history."""
        # NOTE: The aggregate returns a dict on the form
        #   {'history_date__max':
        #    datetime.datetime(2017, 8, 4, 14, 43, 48, 473875, tzinfo=<UTC>)}
        # so we have to dig a little to get it robustly.
        history_date__max_dict = self.history.aggregate(Max("history_date"))
        last_updated = history_date__max_dict.get("history_date__max")
        return last_updated

    @property
    def display_name(self):
        """Produce the best display name we are able to.

        NOTE 1: this is slightly different from medscan-v1, which did

         - Use the actual name if available
         - Or use hostname
         - Or display asset ID + MAC address
         - Or display asset ID + IP address
         - Or display only asset ID
        """
        if self.name:
            d_name = self.name
        elif self.hostname:
            d_name = self.hostname
        elif self.manufacturer:
            if self.model:
                d_name = f"{self.manufacturer}-{self.model}-{self.id}"
            else:
                d_name = f"{self.manufacturer}-{self.id}"
        elif self.oui_manufacturer:
            d_name = f"{self.oui_manufacturer}-{self.id}"
        else:
            d_name = f"Asset-{self.id}"
        return d_name

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

    @display_name.setter
    def display_name(self, value):
        """Set the name of an asset.

        Actually sets the 'name' field, which is favored over other kinds of
        display name in the corresponding getter.
        """
        logger.info("Setting asset name for id=%s to %s", self.id, value)
        self.name = value

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

    def network_qset(self):
        """Return queryset for all networks the asset belongs to.

        To get an actual list of the networks, do self.network_qset().all()
        """
        # Trivial method, in that it's only one line.  But the syntax is
        # not obvious so that's why we have it.
        #
        # FWIW, this is what the query actually looks like:
        #
        # In [*]: print(apps.get_model('blueflow', 'Network').objects.filter(
        #                     cidr__cidr__net_contains='192.168.8.0').query)
        #
        #     SELECT "blueflow_network"."id",
        #            "blueflow_network"."name",
        #            "blueflow_network"."ok_to_scan",
        #            "blueflow_network"."date_added"
        #       FROM "blueflow_network"
        # INNER JOIN "blueflow_cidr"
        #         ON ("blueflow_network"."id" = "blueflow_cidr"."network_id")
        #      WHERE "blueflow_cidr"."cidr" >> 192.168.8.0/32

        if self.ip_address is None:
            # objects.none() gives us an empty QuerySet.
            return apps.get_model("blueflow", "Network").objects.none()

        Network = apps.get_model("blueflow", "Network")
        network_qset = Network.objects.filter(cidr__cidr__net_contains=self.ip_address)
        return network_qset

    @property
    def is_identified(self) -> bool:
        """Determine if asset is identified.

        In order to be "identified" we need to know both manufacturer
        and model.  In addition, we need to know either MAC or IP address.
        """
        # Asset needs BOTH manufacturer & product
        has_man_and_prod = bool(self.manufacturer) and bool(self.model)
        # If Asset now has either IP or MAC it's identified!
        # else, Uh oh, we don't have what's needed to identify
        has_ip_or_mac = bool(self.ip_address) or bool(self.mac_address)
        return has_man_and_prod and has_ip_or_mac

    def scan_qset(self):
        """Return queryset for all scans of the asset.

        To get an actual list of the scans, do self.scan_qset().all()
        """
        Scan = apps.get_model("blueflow", "Scan")
        scan_qset = Scan.objects.filter(asset__id=self.id)
        return scan_qset

    def tag_qset(self):
        """Return queryset for all tags attached to the asset.

        To get an actual list of the tags, do self.tag_qset().all()
        """
        return self.tags.all()

    def similar_qset(self, *, exclude_self=True):
        """Return queryset for all assets similar to this one.

        Two assets are "similar" if they:
         - Share a MAC address range OR
         - Have equal manufacturer & model OR
         - Have the same NIC vendor
        """
        disjuncts = []

        if isinstance(self.mac_address, str):
            self.refresh_from_db()
        if self.mac_address is not None:
            # grab first 3 octets
            octets = self.mac_address.words
            mac_pfx = ":".join(f"{s:02x}" for s in octets[:3])
            min_mac = f"{mac_pfx}:00:00:00"
            max_mac = f"{mac_pfx}:ff:ff:ff"
            disjuncts.append(Q(mac_address__gte=min_mac, mac_address__lte=max_mac))

        if self.manufacturer is not None:
            disjuncts.append(Q(manufacturer=self.manufacturer, product=self.vendor))

        if self.oui_manufacturer is not None:
            disjuncts.append(Q(oui_manufacturer=self.oui_manufacturer))

        Asset = apps.get_model("blueflow", "Asset")
        if disjuncts:
            sim_qset = Asset.objects.filter(reduce(or_, disjuncts))
            if exclude_self:
                sim_qset = sim_qset.exclude(id=self.id)
        else:
            sim_qset = Asset.objects.none()
        return sim_qset

    def history_qset(self):
        """Return queryset for history of asset."""
        return self.history.all()

    def field_history_rqset(self, field_name, *, newest_first=True):
        """Return RAW queryset for history of some asset field.

        Will return only the rows where the field changed.
        """
        # Due to limitations of the Django ORM, we used to rely on raw
        # SQL here, before we turned it into a loop.  It may be that we
        # can optimize and avoid the FROM SELECT subquery... but I don't
        # think so.
        #
        # I just realized that the "first entry" really is a special event
        # in more than one way. If we do decide to revert to the (likely
        # faster) SQL-based query, rather than the loop I added in
        # https://github.com/virtalabs/blueflow/pull/1451/commits/cdf3987644da164bfbb1c505430a96048c4f5cc4,

        # we could simply consistently return the history as "everything
        # but the first" and have a special route for creation/the first
        # element. (But this is premature optimization for sure, so this
        # is just musing.)

        # Validate/sanitize field.
        # NOTE: the get_field might cause a FieldDoesNotExist Django
        #       Exception.  The caller must be prepared to handle this.
        db_field = self.history.model._meta.get_field(field_name)  # noqa: SLF001
        sanitized_field_name = db_field.name
        qset = self.history.order_by("history_date")
        history = [qset[0]]
        for hist_item in qset[1:]:
            if getattr(hist_item, sanitized_field_name) != getattr(
                history[-1], sanitized_field_name
            ):
                history.append(hist_item)
        if newest_first:
            # in-place reverse
            history.reverse()
        return history

    def changelog_qset(self):
        """Return a "change log" for asset.

        It looks mostly like history_qset... except that only the
        field(s) that changed between versions will be non-null.
        """
        qset = self.history
        for field in (f.name for f in self._meta.fields if f.name != "id"):
            # This annotation adds new fields 'name__changed',
            # 'manufacturer__changed', etc.  These fields are `null` iff
            # the corresponding `name` or `manufacturer` are unchanged
            # since the previous row (in the history table.) but
            # identical to the original (e.g. 'name') iff it *has*
            # changed.
            a_kwargs = {field + "__changed": NullUnlessChanged(field)}
            qset = qset.annotate(**a_kwargs)
        # Reverse chronological, i.e., newest-first.
        qset = qset.order_by("-history_date")
        return qset

    def __str__(self):
        return f"{self.id}:{self.display_name}:{self.ip_address}"

    def update_usage(self, timestamp):
        """Record a usage observation for this asset at the given timestamp.

        Looks up (or creates) the Usage row for this asset on
        timestamp.weekday(), then increments the matching hour_NN column —
        unless an observation has already been counted for the same
        Usage.USAGE_WINDOW_MINUTES window, in which case this is a no-op.
        """
        Usage = apps.get_model("blueflow", "Usage")

        window_start = Usage.floor_to_window(timestamp)
        usage, _ = Usage.objects.get_or_create(
            asset=self,
            day_of_week=timestamp.weekday(),
        )
        if usage.last_window_started_at == window_start:
            return
        hour_field = f"hour_{timestamp.hour:02d}"
        setattr(usage, hour_field, getattr(usage, hour_field) + 1)
        usage.last_window_started_at = window_start
        usage.save()

    def todict(self):
        """Return concrete fields as a dictionary for diffing in update_or_create.

        Ported from experimental/testbed-build:bf_opencore/models/asset.py.
        """
        return {f.name: getattr(self, f.attname, None) for f in self._meta.fields}

    def needs_sw_update(self):
        """Return whether this asset needs a software update.

        @returns:
            [needs_update: bool  # needs an update
             latest: string      # latest version number
             versions_in_use: dict<string -> int>]  # count other versions
        """
        needs_update = False

        # bail if this asset doesn't have a parseable version string
        try:
            packaging.version.parse(self.app_sw_version)
            asset_ver_ok = True
        except (packaging.version.InvalidVersion, TypeError):
            asset_ver_ok = False

        vs = (
            self.similar_qset()
            .filter(app_sw_version__isnull=False)
            .values("app_sw_version")
            .annotate(count=Count("app_sw_version"))
        )

        vcounts = Counter({v["app_sw_version"]: v["count"] for v in vs})

        # don't forget to count this asset's app_sw_version
        if self.app_sw_version:
            vcounts[str(self.app_sw_version)] += 1  # count me too

        if vcounts:
            # sort by version number ascending (where
            # packaging.version.Version objects provide the needed comparator)
            versions = sorted(vcounts.keys(), key=packaging.version.parse)
            latest = versions[-1]  # lexically greatest version string
        else:
            latest = self.app_sw_version  # may be None

        # is any of these version numbers greater than ours?
        if asset_ver_ok:
            for ver in vcounts:
                if packaging.version.parse(ver) > packaging.version.parse(
                    self.app_sw_version
                ):
                    needs_update = True
                    break

        return needs_update, latest, dict(vcounts)
