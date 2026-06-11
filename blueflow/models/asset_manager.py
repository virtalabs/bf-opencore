"""BlueFlow Asset Manager.

To accompany the model Asset in asset.py (in this folder).
"""

import logging
from functools import reduce
from operator import or_

from django.apps import apps
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
