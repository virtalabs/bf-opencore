"""BlueFlow Asset Manager.

To accompany the model Asset in asset.py (in this folder).
"""

import logging
from functools import reduce
from operator import or_

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .network import Network

logger = logging.getLogger(__name__)


class AssetManager(models.Manager):
    """Custom manager to query for assets not belonging to a network."""


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
            Asset = apps.get_model("blueflow", "Asset")
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
        Asset = apps.get_model("blueflow", "Asset")
        Cidr = apps.get_model("blueflow", "Cidr")
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

    def _asset_vuln_query(self):
        """Queryset of asset_vulnerabilities attached to these assets."""
        AssetVulnerability = apps.get_model("blueflow", "AssetVulnerability")
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
    if len(field_dict.items()) != 1:
        msg = "Failed to flatten json"
        raise ValueError(msg)
    key, value = next(iter(field_dict.items()))
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
        return {}

    output = {}
    Asset = apps.get_model("blueflow", "Asset")
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
        Asset = apps.get_model("blueflow", "Asset")
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
    old = {} if asset.external_keys is None else asset.external_keys
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
            msg = "external_keys field may not be None"
            raise ValidationError(msg)
        for k, v in value.items():
            if v is None or v == "":
                msg = f"External keys may not be empty or None: {field} {k}={v}"
                raise ValidationError(msg)


def _validate_external_keys_overlap(asset, kwargs, defaults):
    """Raise ValidationError if external_keys in defaults overlap w/ asset."""
    overlap = _external_keys_overlap(asset, defaults)
    if overlap:
        msg = (
            f"Existing asset {asset} matched parameters {kwargs}. "
            f"This asset has external_keys={asset.external_keys} "
            f"and mac_address={asset.mac_address}. "
            f"An update would overwrite external_keys {overlap}. "
            "Refuse to overwrite."
        )
        raise ValidationError(msg)


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
