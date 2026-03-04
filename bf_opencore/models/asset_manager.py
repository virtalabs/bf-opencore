"""BlueFlow Asset Manager.

To accompany the model Asset in asset.py (in this folder).
"""

import logging
import statistics
from collections import defaultdict
from functools import reduce
from operator import or_

from django.apps import apps
from django.core.exceptions import FieldError, ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Coalesce

from bf_opencore.utils import Created

from .network import Network

logger = logging.getLogger(__name__)


class AssetManager(models.Manager):
    """Custom manager to query for assets not belonging to a network."""

    def rescore_all(self):
        """Rescore all assets."""
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Rescore all is not implemented")
        RiskFactor = apps.get_model("bf_opencore", "RiskFactor")
        RiskFactor.objects.normalize_weights()  # Abundance of caution
        summaries = []
        remediable_risk_sum = defaultdict(int)
        remediable_asset_count = defaultdict(int)
        for asset in self.get_queryset().all():
            summaries.append(asset.rescore())
        # Iterate over all the summaries
        # Eng desc of why and what do
        for summary in summaries:
            # Iterate over their entries
            # Eng desc of why and what do
            for entry in summary:
                # Check to see if this stuff is remediable
                if entry["user_remediable"] == "True" and entry["contribution_raw"] > 0:
                    rf_id = entry["rf_id"]
                    # Update the scores
                    # Note: We divide by 2 to get the TOTAL contribution,
                    # rather than just the contribution to cli or sec
                    remediable_risk_sum[rf_id] += entry["contribution_raw"] / 2
                    # Update the number of remediable assets
                    remediable_asset_count[rf_id] += 1
        # We now have the user_remediable information
        # Now, we just need to update it in risk factor
        RiskFactor = apps.get_model("bf_opencore", "RiskFactor")
        for key in remediable_risk_sum:
            rf = RiskFactor.objects.get(id=key)
            rf.remediable_asset_count = remediable_asset_count[key]
            rf.remediable_risk_sum = remediable_risk_sum[key]
            rf.save()

    def get_by_priority(self, **kwargs):
        """Get an Asset, checking kwargs in priority order and ignoring the rest.

        "Priority" here refers to how *exactly* a certain lookup key will
        identify an individual asset. For example, an Asset record bearing a
        certain MAC address will almost certainly refer to only *one* physical
        device throughout its existence. An IP address, on the other hand, may
        be held by more than one physical device over time. So we consider a
        MAC address as having a higher "priority" than the IP address.

        Priority:
        1. external_keys__* (e.g., external_keys__tms, external_keys__aims)
        2. mac_address
        3. ip_address

        kwargs are Asset model fields used to look up an existing Asset object
        in the database.  This the same Djano idiom used by the Djang-provided
        get() function.  Ref:
        https://docs.djangoproject.com/en/2.0/ref/models/querysets/#get
        """
        # Extract the priority parameters. We use Django's get(field=value)
        # with the original parameters provided by the caller of this function,
        # including the double-underscore of the external_keys.

        def valid_val(val):
            """Check if value is valid as a database field.

            Return False if value is None or ""
            Return True if not

            The reason for this function is that '0' is potentially a
            valid field value for the fields in question, thus we can't
            just test for the truth value.
            """
            return False if (val is None) or (val == "") else True

        mac_kwarg = kwargs.pop("mac_address", None)
        ip_kwarg = kwargs.pop("ip_address", None)
        ekeys = [k for k in kwargs if k.startswith("external_keys")]
        if not ekeys:
            ekey_fn, ekey_kwarg = None, None
        elif len(ekeys) == 1:
            ekey_fn = ekeys[0]
            ekey_kwarg = kwargs.pop(ekey_fn)
        elif len(ekeys) > 1:
            # Multiple JSON field keys are not allowed
            #
            # E.g you're not allowed to pass both `external_keys__aims`
            # and `external_keys__tms` in the same call (it would make no
            # sense to do so, anyway.)
            raise FieldError(f"Multiple JSONField keys are not allowed: {ekeys}")

        if not any(valid_val(v) for v in [ekey_kwarg, mac_kwarg, ip_kwarg]):
            raise FieldError(
                "No lookup field provided.  Got: {}.  Expected 1 or more: {}.".format(
                    kwargs.keys(), ("external_keys", "mac_address", "ip_address")
                )
            )

        # Perform lookup in priority order.
        Asset = apps.get_model("bf_opencore", "Asset")
        if valid_val(ekey_kwarg):
            try:
                asset = super().get(**{ekey_fn: ekey_kwarg})
                logger.debug("Matched asset %s on %s=%s", asset, ekey_fn, ekey_kwarg)
                return asset
            except Asset.DoesNotExist:
                # Didn't find asset via external key, try mac
                pass

        if valid_val(mac_kwarg):
            try:
                asset = super().get(mac_address=mac_kwarg)
                logger.debug("Matched asset %s on mac_address=%s", asset, mac_kwarg)
                return asset
            except Asset.DoesNotExist:
                # Didn't find asset via mac, try ip
                pass

        if valid_val(ip_kwarg):
            try:
                asset = super().get(ip_address=ip_kwarg)
            except Asset.MultipleObjectsReturned:
                # Coerce `MultipleObjectsReturned` to `DoesNotExist` when
                # caused by duplicate ip_address and there is a mac_address or
                # external_keys to fall back on.  In this case, the
                # `DoesNotExist` error may later cause a new object to be
                # created, for example, in update_or_create_by_priority().
                if mac_kwarg is not None or ekey_kwarg is not None:
                    raise Asset.DoesNotExist()
                raise  # otherwise re-raise the original exception
            # NOTE: if Asset.DoesNotExist, we want it to be raised here.

            # Decline to clobber mac_address after IP match
            if asset.mac_address and valid_val(mac_kwarg):
                raise Asset.DoesNotExist()

            # Decline to clobber external_keys after IP match
            if asset.external_keys and valid_val(ekey_kwarg):
                raise Asset.DoesNotExist()

            logger.debug("Matched asset %s on ip_address=%s", asset, ip_kwarg)
            return asset

        # Couldn't find it
        raise Asset.DoesNotExist()

    def update_or_create_by_priority(self, defaults=None, **kwargs):
        """Update or create an asset using get_by_priority().

        Returns a tuple of (object, created), where object is the created or
        updated object and created is a boolean specifying whether a new object
        was created.

        This method also elegantly handles JSONField updates.

        Django docs:
        https://docs.djangoproject.com/en/2.0/ref/models/querysets/#update-or-create
        """
        # Remove foreign key fields like asset_risk_factors__* and
        # asset_custom_fields__* from defaults and kwargs
        kwargs, kwargs_fk = _partition_fk_params(kwargs)
        defaults, defaults_fk = _partition_fk_params(defaults)

        # None and empty strings are fatal for external keys
        _validate_external_keys(kwargs)
        _validate_external_keys(defaults)

        # Either get or create an asset using kwargs
        Asset = apps.get_model("bf_opencore", "Asset")
        try:
            asset = self.get_by_priority(**kwargs)
            created = Created.UPDATED
        except Asset.DoesNotExist:
            asset = Asset(**_unflatten_json_params(kwargs))
            created = Created.CREATED

        # Overwriting an external_key is fatal
        _validate_external_keys_overlap(asset, kwargs, defaults)

        # Save a copy before so we can log the changes later
        if not created:
            before = asset.todict()

        # Update asset with defaults.  If the key is a JSONField, then update
        # the dictionary rather than assigning (overwriting) it.
        for key, value in _unflatten_json_params(defaults).items():
            if isinstance(value, dict):
                if getattr(asset, key) is None:
                    setattr(asset, key, dict())
                getattr(asset, key).update(value)
            else:
                setattr(asset, key, value)

        # Save before we attempt to update any foreign key relationships like
        # RiskScore or AssetCustomField.  Django won't let you add a join table
        # entry until the object to be joined (`asset` in this case) is
        # save()'ed to the DB.
        asset.save()

        # Update foreign key relationships
        if created:
            for k, v in kwargs_fk.items():
                asset.update_or_create_fk_field(k, v, reason="created")
        for k, v in defaults_fk.items():
            asset.update_or_create_fk_field(k, v, reason="updated")

        # Avoid later errors when updating the history on this asset.  If you
        # try to hist_utils.update_change_reason(asset, reason) on an asset
        # that is not save()'ed, then you get `AttributeError: 'NoneType'
        # object has no attribute 'history_change_reason'`.  I believe that
        # the new AssetRiskFactor object, which is associated with this Asset,
        # creates the need to save, but I'm not 100% sure.
        #   -- awdeorio 2018-06-22
        asset.save()

        # Log the changes on update.  Assumes before and after have same keys.
        if not created:
            after = asset.todict()
            diff = _dict_diff(before, after)
            if diff:
                created = Created.UPDATED
                logger.debug("Updated asset %s: %s", asset, diff)
            else:
                created = Created.UPTODATE
                logger.debug("Up-to-date asset %s", asset)

        return asset, created


class AssetQuerySet(models.QuerySet):
    """Custom queryset for assets, with some extra methods.

    There are a couple of different types of methods:

      - A "filter on network" method that takes a network ID and returns
        another queryset (for further processing/filtering/etc.)

      - "Aggregate data" type methods, e.g. returning 'identified_statistics'
        or providing details on risk etc. associated with assets in the
        queryset.

    """

    def in_network(self, network_id):
        """Return queryset for asset in a certain network."""
        network = Network.objects.get(id=network_id)
        cidr_disjuncts = (Q(ip_address__net_contained_or_equal=c) for c in network.cidr)
        try:
            qset = self.filter(reduce(or_, cidr_disjuncts))
        except TypeError:
            # This happens if cidr_disjucnts is empty.  In this case we
            # return a special queryset that never returns anything, but
            # otherwise behaves in a robust way.
            Asset = apps.get_model("bf_opencore", "Asset")
            return Asset.objects.none()
        return qset

    def no_network(self):
        """Return queryset for assets not belonging to a network.

        Criteria:

        a) has an IP address assigned and
        b) don't belong to a network

        I.e., there are no CIDRs that match these assets.
        """
        # Start with "full population of assets"
        # First, remove all assets that don't have an IP address.
        nn_qset = self.filter(~Q(ip_address=None))
        # Then, for each CIDR we've registered, remove any asset that matches.
        Asset = apps.get_model("bf_opencore", "Asset")
        Cidr = apps.get_model("bf_opencore", "Cidr")
        for c in Cidr.objects.all():
            nn_qset &= Asset.objects.filter(
                ~Q(ip_address__net_contained_or_equal=c.cidr)
            )
        # The remaining assets don't belong to a network.
        return nn_qset

    def by_network_profile(self, observation):
        """Return queryset matching the netflow record.

        Match by mac address range for now.
        """
        return map(observation.compare, self)

    # The following methods are returning 'aggregate data', i.e., not
    # another queryset.

    def identified_statistics(self):
        """Calculate statistics on identification.

        See the model property is_identified for criteria.
        """
        num = 0
        for asset in self:
            num += int(asset.is_identified)
        if self.count() == 0:
            pct = 0
            not_pct = 0
        else:
            pct = 100.0 * num / self.count()
            not_pct = 100.0 - pct

        return {
            "num": num,
            "not": (self.count() - num),
            "pct": pct,
            "not_pct": not_pct,
        }

    def risk_histogram(self):
        """Return a 'risk histogram'.

        Return a dictionary containing the number of assets in 6 categories:
         - null risk associated (risk_score == null)
         - zero/no risk (risk_score == 0)
         - low (< 0.4)
         - med (< 0.7)
         - high (< 0.9)
         - critical (>= 0.9)

        The first 2 are awkwardly named; this is due to poor naming of
        the fields in the model RiskMetrics.
        """
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Risk histogram is not implemented")
        h = dict(
            critical=self.filter(risk_score__gte=CRITICAL_RISK_LIMIT).count(),
            high=self.filter(
                risk_score__lt=CRITICAL_RISK_LIMIT, risk_score__gte=HIGH_RISK_LIMIT
            ).count(),
            med=self.filter(
                risk_score__lt=HIGH_RISK_LIMIT, risk_score__gte=MED_RISK_LIMIT
            ).count(),
            low=self.filter(risk_score__lt=MED_RISK_LIMIT, risk_score__gt=0.0).count(),
            no=self.filter(risk_score=0.0).count(),
            # null=self.filter(risk_score__isnull=True).count(),
        )
        total_count = sum(h.values())
        if total_count != self.filter(risk_score__isnull=False).count():
            logger.error(
                "Unexpected count when calculating histogram.  "
                "Was '%d', expected '%d'.",
                total_count,
                self.count(),
            )
        return h

    def risk_statistics(self):
        """Return some risk statistics.

        Return a dictionary with the following risk score statistics for
        the assets contained in the queryset:
         - sum
         - mean
         - median
         - max
         - min
         - cli_sum   # sum of safety risk scores
         - cli_mean
         - sec_sum   # sum of security risk scores
         - sec_mean
        """
        # Implementation note 1: Since there's no models.Median aggregate
        #   function, we have to loop over the list of assets and obtain
        #   their risk scores in order to use statistics.median.
        #
        #   Since we're already looping, it might be that it's more
        #   efficient to use regular statistics and python functions to
        #   obtain the other stats as well.
        #
        # Implementeation note 2: Choosing not to return `mode`, because
        #   it's not obvious what to do when there's no unique mode
        #   (statistics.mode will raise a StatisticsError).
        #   (Also because, who other than statistics nerds would even care.)
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Risk statistics is not implemented")
        notnull = self.filter(risk_score__isnull=False)
        if notnull.count() == 0:
            median = None
        else:
            median = statistics.median(a.risk_score for a in notnull)
        s = dict(
            sum=self.aggregate(models.Sum("risk_score"))["risk_score__sum"],
            mean=self.aggregate(models.Avg("risk_score"))["risk_score__avg"],
            max=self.aggregate(models.Max("risk_score"))["risk_score__max"],
            min=self.aggregate(models.Min("risk_score"))["risk_score__min"],
            median=median,
            sec_sum=self.aggregate(val=Coalesce(models.Sum("risk_score_sec"), 0))[
                "val"
            ],
            sec_mean=self.aggregate(val=Coalesce(models.Avg("risk_score_sec"), 0))[
                "val"
            ],
            pri_sum=self.aggregate(val=Coalesce(models.Sum("risk_score_pri"), 0))[
                "val"
            ],
            pri_mean=self.aggregate(val=Coalesce(models.Avg("risk_score_pri"), 0))[
                "val"
            ],
            cli_sum=self.aggregate(val=Coalesce(models.Sum("risk_score_cli"), 0))[
                "val"
            ],
            cli_mean=self.aggregate(val=Coalesce(models.Avg("risk_score_cli"), 0))[
                "val"
            ],
            likelihood_sum=self.aggregate(
                val=Coalesce(models.Sum("risk_score_likelihood"), 0)
            )["val"],
            likelihood_mean=self.aggregate(
                val=Coalesce(models.Avg("risk_score_likelihood"), 0)
            )["val"],
            impact_sum=self.aggregate(val=Coalesce(models.Sum("risk_score_impact"), 0))[
                "val"
            ],
            impact_mean=self.aggregate(
                val=Coalesce(models.Avg("risk_score_impact"), 0)
            )["val"],
        )
        return s

    def risk_factor_statistics(self):
        """Return some statistics on risk factors.

        Return a list of lists that would be used for a histogram.  Each
        element in the list represents a risk factor, and the data in
        each list indicates how many assets have a certain risk factor.
        """
        # TODO: Implement after we have a generalized algorithm for risk scoring
        raise NotImplementedError("Risk factor statistics is not implemented")
        rf_stats = []

        RiskFactor = apps.get_model("bf_opencore", "RiskFactor")
        for fac_type in ["sec", "pri", "cli"]:
            rf_substats = []
            for rf in RiskFactor.objects.filter(factor_type=fac_type):
                rf_substats.append(rf.asset_risk_factor_statistics(self))
                assert "num_affected" in rf_substats[-1]
            rf_substats.sort(
                key=lambda x: (x["weight"] > 0.0, x["num_affected"]), reverse=True
            )
            rf_stats.extend(rf_substats)

        return rf_stats

    def _asset_vuln_query(self):
        """Queryset of asset_vulnerabilities attached to these assets."""
        AssetVulnerability = apps.get_model("bf_opencore", "AssetVulnerability")
        return AssetVulnerability.objects.filter(asset__in=self)

    def vulnerability_statistics(self):
        """Return statistics on vulnerabilities attached to these assets."""
        avulns = self._asset_vuln_query().add_dwell()
        stats = {}
        stats["total"] = avulns.count()
        stats["open"] = avulns.open().count()
        stats["remediated"] = avulns.remediated().count()
        stats["accepted"] = avulns.accepted().count()
        stats["avg_dwell_open"] = avulns.open().avg_dwell()["avg_dwell"]
        # NOTE: 'null' values are ignored when averaging
        avg_dwell = avulns.avg_dwell()
        avg_dwell.pop("avg_dwell")  # Only want accepted and remediated
        stats.update(avg_dwell)
        return stats


################################################################
# Utility functions


def _unflatten_json_field_helper(name, value):
    """Convert one string with JSON field notation to a nested dict."""
    # Base case
    if "__" not in name:
        return {name: value}

    # Recursive step
    key, value_str = name.split("__", maxsplit=1)  # only split on first "__"
    return {key: _unflatten_json_field_helper(value_str, value)}


def _unflatten_json_field(field, value):
    """Return key and value of an JSON field unflattened into a dict."""
    field_dict = _unflatten_json_field_helper(field, value)
    assert len(field_dict.items()) == 1
    key, value = list(field_dict.items())[0]
    return key, value


def _unflatten_json_params(params):
    """Convert JSON field notation with double underscore to nested dict.

    Example:
    Input: {'external_keys__tms': 'X'}
    Output: {'external_keys': {'tms': 'X'}}

    Example:
    Input: {'external_keys__tms': 'X', 'name': 'Drew'}
    Output: {'external_keys': {'tms': 'X'}, 'name': 'Drew'}

    """
    if params is None:
        return dict()

    output = {}
    Asset = apps.get_model("bf_opencore", "Asset")
    for k, v in params.items():
        field, value = _unflatten_json_field(k, v)
        fieldtype = Asset._meta.get_field(field).get_internal_type()
        if fieldtype == "JSONField":
            # Use unflattened values for a JSONField
            if field not in output:
                output[field] = value
            else:
                output[field].update(value)
        else:
            # Don't touch other fields
            output[k] = v
    return output


def _partition_fk_params(params):
    """Partition params that refer to foreign key relationships.

    For example, those starting with 'asset_risk_factors__' or
    'asset_custom_fields__', but *not* those that start with
    'external_keys__'

    Takes a group of parameters in a dictionary, e.g.,

    {
      'ip_address': '10.0.0.1',
      'mac_address': '00:00:00:00:00:01',
      'external_keys__tms': 'abc01',
      'asset_risk_factors__foo': '0.5',
      'asset_custom_fields__location': 'home',
    }

    and returns 2 dictionaries:

    ({
       'ip_address': '10.0.0.1',
       'mac_address': '00:00:00:00:00:01',
       'external_keys__tms': 'abc01',
     },
     {
       'asset_risk_factors__foo': '0.5',
       'asset_custom_fields__location': 'home',
     })

    """
    if params is None:
        return {}, {}

    def is_fk_field(name):
        """Return True if name refers to a foreign key relationship."""
        # Extract 'asset_risk_factors' from 'asset_risk_factors__tms'
        Asset = apps.get_model("bf_opencore", "Asset")
        basename = name.split("__")[0]
        fieldtype = Asset._meta.get_field(basename).get_internal_type()
        return fieldtype == "ForeignKey"

    fk_params = {}
    not_fk_params = {}
    for field_name, value in params.items():
        if is_fk_field(field_name):
            fk_params[field_name] = value
        else:
            not_fk_params[field_name] = value

    return not_fk_params, fk_params


def _external_keys_overlap(asset, defaults):
    """Return overlapping key/values asset.external_keys and defaults."""
    defaults_unflattened = _unflatten_json_params(defaults)
    if "external_keys" not in defaults_unflattened:
        return set()
    new = defaults_unflattened["external_keys"]
    if asset.external_keys is None:
        old = {}
    else:
        old = asset.external_keys
    overlap = set(new.keys()) & set(old.keys())

    # Ignore overlap key if values are the same
    for key in list(overlap):
        if new[key] == old[key]:
            overlap.remove(key)
    return overlap


def _validate_external_keys(params):
    """Raise FieldError if an external_keys are empty or None."""
    for field, value in _unflatten_json_params(params).items():
        if field != "external_keys":
            continue
        if value is None:
            raise ValidationError("external_keys field may not be None")
        for k, v in value.items():
            if v is None or v == "":
                raise ValidationError(
                    f"External keys may not be empty or None: {field} {k}={v}"
                )


def _validate_external_keys_overlap(asset, kwargs, defaults):
    """Raise ValidationError if external_keys in defaults overlap w/ asset."""
    overlap = _external_keys_overlap(asset, defaults)
    if overlap:
        raise ValidationError(
            f"Existing asset {asset} matched parameters {kwargs}. "
            f"This asset has external_keys={asset.external_keys} "
            f"and mac_address={asset.mac_address}. "
            f"An update would overwrite external_keys {overlap}. "
            "Refuse to overwrite.",
        )


def _dict_diff(x, y):
    """Return a dictionary of key-(x[k], y[k]) for values that do not match.

    For keys exclusive to x, map key-(x[k], None).  For keys exclusive to y,
    map key-(None, y[k]).
    """
    diff = {}

    # Keys exclusive to x
    for k in set(x) - set(y):
        diff[k] = (x[k], None)

    # Keys exclusive to y
    for k in set(y) - set(x):
        diff[k] = (None, y[k])

    # Keys in both x and y
    for k in set(x) & set(y):
        if x[k] != y[k]:
            diff[k] = (x[k], y[k])

    return diff
