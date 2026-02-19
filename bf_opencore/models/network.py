"""BlueFlow network.

Also intend to put AssetGroup and SavedSearch here; they all belong
together as "groups of assets".
"""

import logging

from django.db import models
from django.utils import timezone
from django.core import exceptions as d_ex
from netfields import CidrAddressField, NetManager

from django.apps import apps
from bf_opencore.utils import ipset_from_network

logger = logging.getLogger(__name__)


class NetworkManager(models.Manager):
    """Custom manager for creation of a Network.

    Along with a Network, we'll create one or more associated Cidrs.
    The method create_network takes care of this.

    Use as

    new_nwk = Network.objects.create_network(name, cidr)
    """

    @staticmethod
    def create_network(name=None, network=None, ok_to_scan=False):
        """Create a network with associated Cidrs."""
        if network is None:
            raise d_ex.FieldError("No network/cidr field")
        nwk = Network(name=name, ok_to_scan=ok_to_scan)
        nwk.save()
        ipset = ipset_from_network(network)
        for cidr in ipset.iter_cidrs():
            # NOTE: ipset_from_network "normalizes" the CIDR so that
            #   e.g. 10.0.0.14/29 comes out as 10.0.0.8/29
            cidr_record = Cidr(cidr=cidr, network=nwk)
            cidr_record.save()

        return nwk


class Network(models.Model):
    """Holds CIDR-based networks.

    May be a combination of CIDRs, or even single IP addresses.
    The individual CIDRs are stored in the model Cidr.
    """

    name = models.CharField(max_length=126, unique=True)
    ok_to_scan = models.BooleanField(default=False)
    date_added = models.DateTimeField(default=timezone.now)

    objects = NetworkManager()

    @property
    def cidr(self):
        """Collect all CIDRs belonging to this network."""
        # logger.debug("%s:%s - cidr: %s",
        #              self.id, self.name, self.cidr_set.all())
        cidr_list = [str(cidr.cidr) for cidr in self.cidr_set.all()]
        return cidr_list

    @cidr.setter
    def cidr(self, cidr_list):
        """Take a list of CIDRs and associate them with the network.

        When changing, use "crude" approach: simply delete old Cidrs,
        then create new ones.
        """
        current_cidrs = Cidr.objects.filter(network=self)
        current_cidrs.delete()
        for cidr in cidr_list:
            cidr_record = Cidr(cidr=cidr, network=self)
            cidr_record.save()

    @property
    def display_name(self):  # noqa: D102
        if self.name:
            return self.name
        return 'Nwk {}'.format(self.id)

    @property
    def type(self):
        """Return network "type"."""
        return 'cidr'

    @property
    def num_assets(self):
        """Return number of assets in network."""
        Asset = apps.get_model('bf_opencore', 'Asset')
        return Asset.objects.in_network(self.id).count()

    @property
    def identified_statistics(self):
        """Percent identified assets."""
        Asset = apps.get_model('bf_opencore', 'Asset')
        return Asset.objects.in_network(self.id).identified_statistics()

    def __str__(self):  # noqa: D105
        network = ','.join(c for c in self.cidr)
        return "{}:{}:{}".format(self.id, self.name, network)


class Cidr(models.Model):
    """Contains individual CIDRs that make up a network."""

    cidr = CidrAddressField()
    network = models.ForeignKey(Network, on_delete=models.CASCADE)

    objects = NetManager()

    def __str__(self):  # noqa: D105
        return "{}:{}".format(self.id, self.cidr)


class SavedSearch(models.Model):
    """Holds a saved search."""

    name = models.CharField(max_length=126, unique=True)
    search_query = models.JSONField(unique=True)
    ok_to_scan = models.BooleanField(default=False)
    date_added = models.DateTimeField(default=timezone.now)

    def __str__(self):  # noqa: D105
        return "{}:{}:{}".format(self.id, self.name, self.search_query)

    @property
    def search_query_dict(self):
        """Return a dictionary representing the saved search parameters.

        Return {} if there are no saved search parameters.
        """
        if self.search_query is None:
            return {}
        return dict(self.search_query)
