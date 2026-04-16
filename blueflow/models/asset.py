"""Blueflow Asset model / schema.

Note: AssetManager has been moved to its own file asset_manager.py.
"""

import logging
from collections import Counter
from functools import reduce
from operator import or_

import django.contrib.postgres.fields as pg_fields
import netaddr
import packaging.version
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, Max, Q
from django.utils import timezone
from netfields import InetAddressField, MACAddressField
from simple_history import utils as hist_utils
from simple_history.models import HistoricalRecords

from blueflow.utils import NullUnlessChanged

from .asset_custom_field import AssetCustomField, AssetCustomFieldName
from .asset_manager import AssetManager, AssetQuerySet, _unflatten_json_field
from .group import AssetGroup, Group
from .tag import AssetTag, Tag
from .vulnerability import AssetVulnerability, Vulnerability

logger = logging.getLogger(__name__)


class Asset(models.Model):
    """Holds our Assets."""

    name = models.CharField(max_length=126, blank=True, null=True)
    # 'hostname' for sure does not need to be unique.
    hostname = models.TextField(blank=True, null=True)
    ip_address = InetAddressField(
        store_prefix_length=False, blank=True, null=True, verbose_name="IP address"
    )
    mac_address = MACAddressField(
        blank=True, null=True, unique=True, verbose_name="MAC address"
    )
    nic_vendor = models.TextField(blank=True, null=True, verbose_name="NIC vendor")
    manufacturer = models.TextField(blank=True, null=True)
    model = models.TextField(blank=True, null=True)
    serial_number = models.TextField(blank=True, null=True)
    udi = models.TextField(blank=True, null=True, verbose_name="UDI")
    tag_number = models.TextField(blank=True, null=True)
    category = models.TextField(blank=True, null=True)

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
    owner = models.TextField(blank=True, null=True)
    os = models.TextField(blank=True, null=True, verbose_name="Operating System")
    app_sw_version = models.TextField(
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
    history = HistoricalRecords()

    # Our manager is a meld of AssetManager and the methods from AssetQuerySet
    # https://docs.djangoproject.com/en/2.0/topics/db/managers/#from-queryset
    objects = AssetManager.from_queryset(AssetQuerySet)()

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
        try:
            # Newports might be a single port as a string
            newports = [int(newports)]
        except TypeError:
            # Looks like it wasn't
            pass
        newports = {int(p) for p in newports}
        ports = sorted(set.union(set(self.open_ports_tcp), newports))
        if ports != self.open_ports_tcp:
            added = set(ports) - set(self.open_ports_tcp)
            # The new list of ports is larger
            assert added != set()
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
        if self.ip_address:
            return True
        if self.mac_address:
            return True
        # Uh oh, we don't have what's needed to identify
        return False

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

    def similar_qset(self, exclude_self=True):
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

    def field_history_rqset(self, field_name, newest_first=True):
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
        db_field = self.history.model._meta.get_field(field_name)
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
        # TODO(taylorcochran): Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Update or create fk field is not implemented")
        # Parse name
        assert "__" in name, f"Expected '__' in fk field {name}"
        asset_field, fk_name = name.split("__", maxsplit=1)
        fieldtype = Asset._meta.get_field(asset_field).get_internal_type()
        assert fieldtype == "ForeignKey", (
            f"Expected '{fk_name}' of '{name}' to be a ForeignKey.  Got {fieldtype}."
        )

        # Get AssetCustomFieldName object using either 'asset_custom_fields__*'
        # notation or the human-readable name.
        if asset_field == "asset_custom_fields":
            # Custom fields names may contain spaces.  Support names with
            # spaces replaced by underscore
            fk_name_regex = fk_name.replace("_", "[ _]")
            try:
                field = AssetCustomFieldName.objects.get(
                    field_name__regex=fk_name_regex
                )
            except AssetCustomFieldName.DoesNotExist:
                raise AssetCustomFieldName.DoesNotExist(
                    f"Cannot add unknown custom field {name} to asset {self}",
                )
            # Create or update the AssetCustomField object
            acf, _ = self.asset_custom_fields.update_or_create(
                asset=self,
                field=field,
                defaults={
                    "value_text": value,
                },
            )
            if reason is not None:
                hist_utils.update_change_reason(acf, reason)
        elif asset_field == "asset_risk_factors":
            try:
                rfac = RiskFactor.objects.get(shortname=fk_name)
            except RiskFactor.DoesNotExist:
                raise RiskFactor.DoesNotExist(
                    f"Cannot add unknown risk factor {name} to asset {self}",
                )
            # Coerce value=None and value="" to value=0.0.  This might occur if
            # a connector reads this value through a field mapping and the
            # external database contains an empty string.
            if value is None:
                logger.debug(
                    "Coercing risk factor '%s' from '%s' to 0.0",
                    name,
                    value,
                )
                value = 0.0
            # Nicer error message for non-numbers
            try:
                value = float(value)
            except TypeError:
                raise ValidationError(f"Not a valid risk factor value: {value}")
            arf, _ = self.asset_risk_factors.update_or_create(
                asset=self,
                risk_factor=rfac,
                defaults={"value": value},
            )
            if reason is not None:
                hist_utils.update_change_reason(arf, reason)
        else:
            assert False, f"Unsupported foreign key: '{asset_field}'"

    @staticmethod
    def is_valid_field_name(name):
        """Return True if name is a valid Asset field.

        Django documentation:
        https://docs.djangoproject.com/en/2.0/ref/models/meta/#retrieving-all-field-instances-of-a-model
        """
        # TODO(taylorcochran): Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Is valid field name is not implemented")
        Asset = apps.get_model("blueflow", "Asset")
        valid_field_names = [x.name for x in Asset._meta.get_fields()]
        unflattened_field_name, _ = _unflatten_json_field(name, None)
        return bool(unflattened_field_name in valid_field_names)

    @staticmethod
    def is_valid_field_value(field, value):
        """Return True if value is valid for field."""
        # TODO(taylorcochran): Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Is valid field value is not implemented")
        unflattened_field, unflattened_val = _unflatten_json_field(field, value)
        # Special case for asset_risk_factors__<RiskFactor shortname>
        if unflattened_field == "asset_risk_factors":
            assert len(unflattened_val.items()) == 1
            shortname = next(iter(unflattened_val.items()))[0]
            try:
                _ = RiskFactor.objects.get(shortname=shortname)
            except RiskFactor.DoesNotExist:
                return False
            try:
                _ = float(value)
            except ValueError:
                return False
            return True

        # Special case for asset_custom_fields__<custom field name>
        if unflattened_field == "asset_custom_fields":
            assert len(unflattened_val.items()) == 1
            shortname = next(iter(unflattened_val.items()))[0]
            # Custom fields names may contain spaces.  Support names with
            # spaces replaced by underscore
            fk_name_regex = shortname.replace("_", "[ _]")
            try:
                AssetCustomFieldName.objects.get(field_name__regex=fk_name_regex)
            except AssetCustomFieldName.DoesNotExist:
                return False
            return True

        # "Stupid" django ORM trick: see what type django would assign to this
        # value on Asset.save(), and validate value against that type.
        Asset = apps.get_model("blueflow", "Asset")
        try:
            orm_field = Asset._meta.get_field(unflattened_field)
            _ = orm_field.get_prep_value(unflattened_val)
        except ValidationError:
            return False
        return True

    def __str__(self):
        return f"{self.id}:{self.display_name}:{self.ip_address}"

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
            for ver in vcounts.keys():
                if packaging.version.parse(ver) > packaging.version.parse(
                    self.app_sw_version
                ):
                    needs_update = True
                    break

        return needs_update, latest, dict(vcounts)
