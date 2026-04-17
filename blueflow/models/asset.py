"""Blueflow Asset model / schema.

Note: AssetManager has been moved to its own file asset_manager.py.
"""

import contextlib
import logging
import math
from collections import Counter
from functools import reduce
from operator import or_

import django.contrib.postgres.fields as pg_fields
import netaddr
import packaging.version
from django.apps import apps
from django.db import models
from django.db.models import Count, Max, Q
from django.utils import timezone
from netfields import InetAddressField, MACAddressField
from simple_history.models import HistoricalRecords

from blueflow.utils import NullUnlessChanged

from .asset_custom_field import AssetCustomField, AssetCustomFieldName
from .asset_manager import AssetManager, AssetQuerySet
from .group import AssetGroup, Group
from .tag import AssetTag, Tag
from .vulnerability import AssetVulnerability, Vulnerability

logger = logging.getLogger(__name__)


class Asset(models.Model):
    """Holds our Assets."""

    name = models.CharField(max_length=126, blank=True, null=True)  # noqa: DJ001
    # 'hostname' for sure does not need to be unique.
    hostname = models.TextField(blank=True, null=True)  # noqa: DJ001
    ip_address = InetAddressField(
        store_prefix_length=False, blank=True, null=True, verbose_name="IP address"
    )
    mac_address = MACAddressField(
        blank=True, null=True, unique=True, verbose_name="MAC address"
    )
    nic_vendor = models.TextField(blank=True, null=True, verbose_name="NIC vendor")  # noqa: DJ001
    manufacturer = models.TextField(blank=True, null=True)  # noqa: DJ001
    model = models.TextField(blank=True, null=True)  # noqa: DJ001
    serial_number = models.TextField(blank=True, null=True)  # noqa: DJ001
    udi = models.TextField(blank=True, null=True, verbose_name="UDI")  # noqa: DJ001
    tag_number = models.TextField(blank=True, null=True)  # noqa: DJ001
    category = models.TextField(blank=True, null=True)  # noqa: DJ001

    # overall risk score and sub-scores for "safety" & "security"
    risk_score = models.FloatField(blank=True, null=True)
    risk_score_cli = models.FloatField(
        blank=True, null=True, verbose_name="Safety risk score"
    )
    risk_score_sec = models.FloatField(
        blank=True, null=True, verbose_name="Security risk score"
    )
    risk_score_pri = models.FloatField(
        blank=True, null=True, verbose_name="Privacy risk score"
    )

    risk_score_likelihood = models.FloatField(
        blank=True, null=True, verbose_name="Likelihood risk score"
    )
    risk_score_impact = models.FloatField(
        blank=True, null=True, verbose_name="Impact risk score"
    )

    date_added = models.DateTimeField(default=timezone.now)
    owner = models.TextField(blank=True, null=True)  # noqa: DJ001
    os = models.TextField(blank=True, null=True, verbose_name="Operating System")  # noqa: DJ001
    app_sw_version = models.TextField(  # noqa: DJ001
        blank=True, null=True, verbose_name="Application software version"
    )
    last_scanned = models.DateTimeField(blank=True, null=True)
    last_pinged = models.DateTimeField(blank=True, null=True)
    open_ports_tcp = pg_fields.ArrayField(
        models.IntegerField(), default=list, verbose_name="Open TCP ports"
    )
    external_keys = models.JSONField(blank=True, null=True)

    groups = models.ManyToManyField(Group, through=AssetGroup)
    tags = models.ManyToManyField(Tag, through=AssetTag)
    vulnerabilities = models.ManyToManyField(Vulnerability, through=AssetVulnerability)
    custom_fields = models.ManyToManyField(
        AssetCustomFieldName, through=AssetCustomField
    )
    risk_score_remediable = models.FloatField(null=False, default=0.0)

    # note: Asset.custom_fields defined in AssetCustomField class
    # note: Asset.asset_tags defined in AssetTag class
    # note: Asset.asset_vulnerabilities defined in AssetVulnerability class
    # note: Asset.asset_risk_factors defined in AssetRiskFactor class

    history = HistoricalRecords()

    # Our manager is a meld of AssetManager and the methods from AssetQuerySet
    # https://docs.djangoproject.com/en/2.0/topics/db/managers/#from-queryset
    objects = AssetManager.from_queryset(AssetQuerySet)()

    def __str__(self):
        return f"{self.id}:{self.display_name}:{self.ip_address}"

    def save(self, *args, **kwargs):
        """Intercept save, automatically populating some fields."""
        if self.mac_address:
            try:
                eui = netaddr.EUI(self.mac_address)
                reg = eui.oui.registration()
                self.nic_vendor = reg.org.strip()
            except netaddr.core.AddrFormatError:
                logger.warning("Bad MAC address on asset %s", self)
                self.nic_vendor = None
            except netaddr.core.NotRegisteredError:
                logger.info(
                    "MAC address %s of asset %s lacks NIC vendor",
                    self.mac_address,
                    self,
                )
                self.nic_vendor = None
            except AttributeError:  # no reg.org
                logger.debug(
                    "NIC vendor registry lacks org detail for MAC address %s",
                    self.mac_address,
                )
                self.nic_vendor = None

        super().save(*args, **kwargs)

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
        elif self.nic_vendor:
            d_name = f"{self.nic_vendor}-{self.id}"
        else:
            d_name = f"Asset-{self.id}"
        return d_name

    @display_name.setter
    def display_name(self, value):
        """Set the name of an asset.

        Actually sets the 'name' field, which is favored over other kinds of
        display name in the corresponding getter.
        """
        logger.info("Setting asset name for id=%s to %s", self.id, value)
        self.name = value

    def open_ports_tcp_add(self, newports):
        """Add one or many ports to the list of open TCP ports.

         'newports' may be an integer (possibly as string) or list of integers.

        Maintains self.open_ports_tcp as a sorted list with no duplicates.

        Returns True if any ports were added to the set, False otherwise.
        """
        with contextlib.suppress(TypeError):
            # Newports might be a single port as a string
            newports = [int(newports)]
        newports = {int(p) for p in newports}
        ports = sorted(set.union(set(self.open_ports_tcp), newports))
        if ports != self.open_ports_tcp:
            added = set(ports) - set(self.open_ports_tcp)
            # The new list of ports is larger
            assert added != set()  # noqa: S101
            logger.debug("Added new TCP ports %s", added)
            self.open_ports_tcp = ports
            return True
        return False

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
    def is_identified(self):
        """Determine if asset is identified.

        In order to be "identified" we need to know both manufacturer
        and model.  In addition, we need to know either MAC or IP address.
        """
        # Asset needs BOTH manufacturer & model
        if not self.manufacturer:
            return False
        if not self.model:
            return False
        # If Asset now has either IP or MAC it's identified!
        return bool(self.ip_address or self.mac_address)

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
            disjuncts.append(Q(manufacturer=self.manufacturer, model=self.model))

        if self.nic_vendor is not None:
            disjuncts.append(Q(nic_vendor=self.nic_vendor))

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

    def get_risk_factor(self, shortname):
        """Fetch an asset risk factor.

        Returns None if there is no such risk factor or this asset does not
        have the given risk factor associated with it (via AssetRiskFactor).
        """
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Get risk factor is not implemented"
        raise NotImplementedError(msg)

    def add_risk_factor(self, shortname, value, reason=None):
        """Add or replace a risk score factor for this Asset."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Add risk factor is not implemented"
        raise NotImplementedError(msg)

    def remove_risk_factor(self, shortname, reason=None):
        """Remove a risk score factor from this Asset."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Remove risk factor is not implemented"
        raise NotImplementedError(msg)

    def update_or_create_fk_field(self, name, value, reason=None):
        """Update or create a foreign key field with '__' notation.

        Examples:
        update_or_create_fk_field(
            name='asset_risk_score__tms',
            value=5.7,
        )
        update_or_create_fk_field(
            name='asset_custom_fields__location',
            value='Main Hospital',
        )

        """
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Update or create fk field is not implemented"
        raise NotImplementedError(msg)

    @staticmethod
    def _soft_clip(x, rmax=10, rmin=0, a=1, typ="arctan"):
        """Limit input argument x to [0, rmax).

        Domain of x is supposed to be [0, ∞).

        If supplied x < 0, then the output is undefined (and may raise
        exceptions).

        There are 2 types: 'arctan' and 'inv_x'.  Se code for specific
        definition.  Either takes an argument `a` which determines the
        slope.
        """
        assert rmin == 0, "Not set up to handle rmin != 0"  # noqa: S101

        x = x / rmax
        if typ == "arctan":
            clipped = math.atan(a * x) / (math.pi / 2)
        elif typ == "inv_x":
            clipped = 1 - (1 / ((a * x) + 1))
        else:
            msg = f"'typ' must be 'arctan' or 'inv_x'; was {typ}"
            raise ValueError(msg)
        return clipped * rmax

    def _update_cvss_risk(self):
        """Update the cvss risk factors from associated vulnerabilities."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Update cvss risk is not implemented"
        raise NotImplementedError(msg)

    def _update_patch_risk(self):
        """Update the patch risk AssetRiskFactor using needs_sw_update()."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Update patch risk is not implemented"
        raise NotImplementedError(msg)

    def asset_risk_factors_with_zeros(self):
        """Return a list of AssetRiskFactor's, including those with zero value.

        All risk factors are included.  If an AssetRiskFactor is associated
        with this asset, use that.  Otherwise, create a dummy AssetRiskFactor
        object, automatically initialized with a default value.  This dummy
        object is not saved to the database.  We need the dummy objects
        for things like inverted risky tags.  If a tag is *not present*,
        that contributes a non-zero value to the risk score.
        """
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Asset risk factors with zeros is not implemented"
        raise NotImplementedError(msg)

    def _calculate_risk(self):
        """Calculate aggregate risk score for an asset."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Calculate risk is not implemented"
        raise NotImplementedError(msg)

    def risk_score_summary(self):
        """Return summary only (to avoid 'protected access')."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Risk score summary is not implemented"
        raise NotImplementedError(msg)

    def rescore(self, reason="Rescore", *, save_reason=True):
        """Update the risk_score field with a newly calculated score."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Rescore is not implemented"
        raise NotImplementedError(msg)

    @classmethod
    def rescore_asset_on_save(  # noqa: PLR0913
        cls, sender, instance, created, raw, using, update_fields, *args, **kwargs
    ):
        """Rescore an asset via a Django signal."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Rescore asset on save is not implemented"
        raise NotImplementedError(msg)

    @staticmethod
    def rescore_asset_on_delete(sender, instance, using, *args, **kwargs):
        """Rescore an asset via a Django signal."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Rescore asset on delete is not implemented"
        raise NotImplementedError(msg)

    @staticmethod
    def is_valid_field_name(name):
        """Return True if name is a valid Asset field.

        Django documentation:
        https://docs.djangoproject.com/en/2.0/ref/models/meta/#retrieving-all-field-instances-of-a-model
        """
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Is valid field name is not implemented"
        raise NotImplementedError(msg)

    @staticmethod
    def is_valid_field_value(field, value):
        """Return True if value is valid for field."""
        # TODO(#9): implement risk scoring  # noqa: FIX002
        msg = "Is valid field value is not implemented"
        raise NotImplementedError(msg)

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
