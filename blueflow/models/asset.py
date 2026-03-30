"""Blueflow Asset model / schema.

Note: AssetManager has been moved to its own file asset_manager.py.
"""

import logging
import math
from collections import Counter
from functools import reduce
from operator import or_

import django.contrib.postgres.fields as pg_fields
import netaddr
import packaging.version
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, transaction
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
    # note: Asset.asset_risk_factors defined in AssetRiskFactor class

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

    def get_risk_factor(self, shortname):
        """Fetch an asset risk factor.

        Returns None if there is no such risk factor or this asset does not
        have the given risk factor associated with it (via AssetRiskFactor).
        """
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Get risk factor is not implemented")
        # TODO: this function is only used in tests and in
        #   `remove_risk_factor`.  Consider removing it altogether...?
        #   TBH, even remove_risk_factor could/should be removed, it's
        #   only used in this file to remove cvss_max and cvss_sum.
        try:
            rfac = RiskFactor.objects.get(shortname=shortname)
            return AssetRiskFactor.objects.get(asset=self, risk_factor=rfac)
        except (RiskFactor.DoesNotExist, AssetRiskFactor.DoesNotExist):
            return None

    def add_risk_factor(self, shortname, value, reason=None):
        """Add or replace a risk score factor for this Asset."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Add risk factor is not implemented")
        # Get RiskFactor object using either 'asset_risk_factor__*' notation
        # or the human-readable name.
        try:
            rfac = RiskFactor.objects.get(shortname=shortname)
        except RiskFactor.DoesNotExist:
            raise RiskFactor.DoesNotExist(
                f"Cannot add unknown risk factor {shortname} to asset {self}",
            )

        # Create or update the AssetRiskFactor object
        arf, _ = self.asset_risk_factors.update_or_create(
            asset=self,
            risk_factor=rfac,
            defaults={
                "value": value,
                "provenance": reason,
            },
        )
        if reason is not None:
            hist_utils.update_change_reason(arf, reason)

    def remove_risk_factor(self, shortname, reason=None):
        """Remove a risk score factor from this Asset."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Remove risk factor is not implemented")
        arf = self.get_risk_factor(shortname)
        if arf is not None:
            arf.delete()
            if reason is not None:
                hist_utils.update_change_reason(arf, reason)

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
        # TODO: Implement after we have a generalized algorithm for risk scoring
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
    def _soft_clip(x, rmax=10, rmin=0, a=1, typ="arctan"):
        """Limit input argument x to [0, rmax).

        Domain of x is supposed to be [0, ∞).

        If supplied x < 0, then the output is undefined (and may raise
        exceptions).

        There are 2 types: 'arctan' and 'inv_x'.  Se code for specific
        definition.  Either takes an argument `a` which determines the
        slope.
        """
        assert rmin == 0, "Not set up to handle rmin != 0"

        x = x / rmax
        if typ == "arctan":
            clipped = math.atan(a * x) / (math.pi / 2)
        elif typ == "inv_x":
            clipped = 1 - (1 / ((a * x) + 1))
        else:
            raise ValueError(f"'typ' must be 'arctan' or 'inv_x'; was {typ}")
        return clipped * rmax

    def _update_cvss_risk(self):
        """Update the cvss risk factors from associated vulnerabilities."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Update cvss risk is not implemented")
        # cvss scores from vulnerabilities hanging off this (may be empty)
        vuln_scores = [
            av.vulnerability.cvss_score
            for av in self.asset_vulnerabilities.open()
            if av.vulnerability.cvss_score is not None
        ]

        if vuln_scores:
            self.add_risk_factor("cvss_max", max(vuln_scores))
            self.add_risk_factor("cvss_sum", self._soft_clip(sum(vuln_scores)))
        else:
            self.remove_risk_factor("cvss_max")
            self.remove_risk_factor("cvss_sum")

    def _update_patch_risk(self):
        """Update the patch risk AssetRiskFactor using needs_sw_update()."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Update patch risk is not implemented")
        needs_update, dummy, dummy = self.needs_sw_update()
        if needs_update:
            self.add_risk_factor("needs_patch", 1.0)
        else:
            self.remove_risk_factor("needs_patch")

    def asset_risk_factors_with_zeros(self):
        """Return a list of AssetRiskFactor's, including those with zero value.

        All risk factors are included.  If an AssetRiskFactor is associated
        with this asset, use that.  Otherwise, create a dummy AssetRiskFactor
        object, automatically initialized with a default value.  This dummy
        object is not saved to the database.  We need the dummy objects
        for things like inverted risky tags.  If a tag is *not present*,
        that contributes a non-zero value to the risk score.
        """
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Asset risk factors with zeros is not implemented")
        factors = []
        for risk_factor in RiskFactor.enabled.all():
            try:
                arf = self.asset_risk_factors.get(
                    risk_factor_id=risk_factor.id,
                )
            except AssetRiskFactor.DoesNotExist:
                arf = AssetRiskFactor(asset=self, risk_factor=risk_factor)
            factors.append(arf)
        return factors

    # Protect this asset's risk-scoring ingredients from changes to RiskFactors
    # that happen during global rescore. This scenario arises when, for
    # instance, the user has just saved risk factor weights and then
    # decides to delete a tag.
    @transaction.atomic
    def _calculate_risk(self):
        """Calculate aggregate risk score for an asset."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Calculate risk is not implemented")

    def risk_score_summary(self):
        """Return summary only (to avoid 'protected access')."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Risk score summary is not implemented")
        dummy_rft_scores, summary = self._calculate_risk()
        return summary

    def rescore(self, reason="Rescore", save_reason=True):
        """Update the risk_score field with a newly calculated score."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Rescore is not implemented")
        self._update_cvss_risk()
        self._update_patch_risk()
        rft_scores, summary = self._calculate_risk()

        # Get our total remediable score
        risk_score_remediable = 0
        for risk_factor in summary:
            if risk_factor["user_remediable"] == "True":
                risk_score_remediable += risk_factor["contribution_raw"] / 2

        need_to_save = False
        if self.risk_score != rft_scores["total_risk_score"]:
            self.risk_score = rft_scores["total_risk_score"]
            need_to_save = True
        if self.risk_score_cli != rft_scores["cli"]:
            self.risk_score_cli = rft_scores["cli"]
            need_to_save = True
        if self.risk_score_sec != rft_scores["sec"]:
            self.risk_score_sec = rft_scores["sec"]
            need_to_save = True
        if self.risk_score_pri != rft_scores["pri"]:
            self.risk_score_pri = rft_scores["pri"]
            need_to_save = True
        if self.risk_score_likelihood != rft_scores["likelihood"]:
            self.risk_score_likelihood = rft_scores["likelihood"]
            need_to_save = True
        if self.risk_score_impact != rft_scores["impact"]:
            self.risk_score_impact = rft_scores["impact"]
            need_to_save = True
        if self.risk_score_remediable != risk_score_remediable:
            self.risk_score_remediable = risk_score_remediable
            need_to_save = True

        if need_to_save:
            self.save()
            if save_reason:
                hist_utils.update_change_reason(self, reason)

        return summary

    @classmethod
    def rescore_asset_on_save(
        cls, sender, instance, created, raw, using, update_fields, *args, **kwargs
    ):
        """Rescore an asset via a Django signal."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Rescore asset on save is not implemented")
        # Don't rescore if we're loading a fixture (i.e., we're in "raw" mode)
        if raw:
            logger.debug("Raw Asset (id %s), not rescoring", instance.id)
            return

        # Rescore if asset was created or if app_sw_version changed.  Also
        # rescore similar assets.
        #
        # NOTE: unfortunately, update_fields doesn't appear to be used.  Its
        # value seems to be None all the time, which indicates "save them all"
        # Thus, we rescore() if an app_sw_version is present.  In a perfect
        # world, we'd rescore only if app_sw_version changed.
        #
        # NOTE: We could get a cycle, where updating an asset causing an update
        # to similar assets, which in turn causes an update to the original
        # asset, ad infinitum.  I add an attribute "norecurse" to break this
        # cycle.  It's kind of a hack, basically marking assets as "visited"
        # which is a base case in the BFS.
        if created or instance.app_sw_version:
            logger.debug("rescoring after Asset save %s", instance)
            instance.rescore(save_reason=False)
            if getattr(instance, "norecurse", None):
                # HACK break cycle
                return
            for asset in instance.similar_qset():
                logger.debug("rescoring similar asset %s", asset)
                asset.norecurse = True  # HACK break cycle
                asset.rescore(reason="Rescore similar assets")

    @staticmethod
    def rescore_asset_on_delete(sender, instance, using, *args, **kwargs):
        """Rescore an asset via a Django signal."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Rescore asset on delete is not implemented")
        # Rescore similar assets if the deleted asset had a sw version
        if instance.app_sw_version:
            for asset in instance.similar_qset():
                logger.debug("rescoring similar asset after delete %s", asset)
                asset.rescore()

    @staticmethod
    def is_valid_field_name(name):
        """Return True if name is a valid Asset field.

        Django documentation:
        https://docs.djangoproject.com/en/2.0/ref/models/meta/#retrieving-all-field-instances-of-a-model
        """
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Is valid field name is not implemented")
        Asset = apps.get_model("blueflow", "Asset")
        valid_field_names = [x.name for x in Asset._meta.get_fields()]
        unflattened_field_name, _ = _unflatten_json_field(name, None)
        return bool(unflattened_field_name in valid_field_names)

    @staticmethod
    def is_valid_field_value(field, value):
        """Return True if value is valid for field."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Is valid field value is not implemented")
        unflattened_field, unflattened_val = _unflatten_json_field(field, value)
        # Special case for asset_risk_factors__<RiskFactor shortname>
        if unflattened_field == "asset_risk_factors":
            assert len(unflattened_val.items()) == 1
            shortname = list(unflattened_val.items())[0][0]
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
            shortname = list(unflattened_val.items())[0][0]
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
        return {f.name: getattr(self, f.attname, None) for f in self._meta.fields}  # noqa: SLF001

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

        vcounts = Counter(dict((v["app_sw_version"], v["count"]) for v in vs))

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
            for ver, _ in vcounts.items():
                if packaging.version.parse(ver) > packaging.version.parse(
                    self.app_sw_version
                ):
                    needs_update = True
                    break

        return needs_update, latest, dict(vcounts)
