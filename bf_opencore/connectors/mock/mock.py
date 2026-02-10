# Copyright (C) 2017 Virta Laboratories, Inc.  All rights reserved.

"""Utility for creating assets."""

import random
from datetime import timedelta
import json
import importlib

import celery
import netaddr

from django.apps import apps
from simple_history import utils as hist_utils
from django.utils import timezone


logger = celery.utils.log.get_task_logger(__name__)

MATH_PACKAGE_ERROR = ("Mock connector needs 'numpy'.  "
                      "Install with `pip install numpy` and try again. ")
CHANGE_REASON = "Random Asset Generator"


def random_hex():
    """Produce a random color from the venerable "every color" colormap.

    https://twitter.com/everycolorbot
    """
    return '#{:06x}'.format(random.randint(0, 2**24 - 1))


def network_cidr(network):
    """From a Network object, extract only the first CIDR (if any).

    This is made as a function on the Network, not as a method, since
    it's a hack that's only relevant for this mock generator script.
    """
    cidr_list = network.cidr
    if len(cidr_list) > 1:
        logger.warning("CIDRs covers more than one range (%s). "
                       "We use only the first.", cidr_list)
    try:
        cidr = cidr_list[0]
    except IndexError:
        logger.warning("No IPs in CIDR list: %s", cidr_list)
        return None
    cidr = netaddr.IPNetwork(cidr)
    return cidr


class MockPopulation():
    """Represents a population of generated assets."""

    # we use lots of self.* variables
    # pylint: disable=too-many-instance-attributes

    def __init__(self, config_dict, num_manufacturers=None):
        """Create population."""
        self.config_dict = config_dict
        self._create_networks()
        self._create_tags()
        self._create_risk_factors()
        self._create_vulnerabilities()

        try:
            self.np = importlib.import_module('numpy')
        except ImportError:
            logger.error(MATH_PACKAGE_ERROR)
            raise

        total_addrs = sum(len(network_cidr(nwk)) for nwk in self.networks)
        print('Population distribution:')
        for nwk in self.networks:
            nwk.weight = len(network_cidr(nwk)) / total_addrs
            print(' * {:.<25s} {:4.1f} %'.format(nwk.name, nwk.weight * 100.0))

        manuf_dict = {}
        if num_manufacturers is not None:
            manufacturers = list(self.config_dict['manufacturers'])
            rand_man = self.np.random.choice(manufacturers, num_manufacturers)
            for manuf in rand_man:
                manuf_dict[manuf] = self.config_dict['manufacturers'][manuf]
        else:
            manuf_dict.update(self.config_dict['manufacturers'])

        self.manufacturers = []
        self.mac_ranges = {}
        for manufacturer, asset_models in manuf_dict.items():
            # generate a random MAC address range start (set first 3 octets)
            mac_range = self.np.random.randint(0, 2**48 - 1) & (0xffffff << 24)
            self.mac_ranges[manufacturer] = mac_range
            for asset_model in asset_models:
                self.manufacturers.append((manufacturer, asset_model))

        self.oses = self.config_dict['os']
        self.owners = self.config_dict['owners']

    @classmethod
    def from_file(cls, filename, *args, **kwargs):
        """Create a MockPopulation instance from a configuration file."""
        config_dict = {}
        with open(filename, 'r') as jsonfp:
            config_dict.update(json.load(jsonfp))
        return cls(config_dict, *args, **kwargs)

    def _create_tags(self):
        """Create tags as specified in config_dict['tags']."""
        self.tags = []
        AssetTag = apps.get_model('bf_opencore', 'AssetTag')
        tag_config = self.config_dict.get('tags', {})
        for name, config in tag_config.items():
            try:
                tag = AssetTag.objects.get(name=name)
            except AssetTag.DoesNotExist:
                color = config.get('color', random_hex())
                tag = AssetTag(name=name, color=color)
                tag.save()
                hist_utils.update_change_reason(tag, CHANGE_REASON)

            # Allowed to save extra attrib temporarily
            tag.percent = config['percent']
            self.tags.append(tag)

    def _create_networks(self):
        """Create network records for mock assets."""
        self.networks = []
        Network = apps.get_model('bf_opencore', 'Network')
        for name, cidr in self.config_dict['networks'].items():
            try:
                nwk = Network.objects.filter(name=name)[0]
            except IndexError:
                nwk = Network.objects.create_network(name, cidr)
            self.networks.append(nwk)

    def _create_risk_factors(self):
        """Create risk factors according to config."""
        self.risk_factors = []
        RiskFactor = apps.get_model('bf_opencore', 'RiskFactor')
        rf_config = self.config_dict.get('risk_factors', {})
        for name, config in rf_config.items():
            percent = config.pop('percent')
            try:
                rf = RiskFactor.objects.get(name=name)
            except RiskFactor.DoesNotExist:
                rf = RiskFactor.objects.create(name=name, **config)
                hist_utils.update_change_reason(rf, CHANGE_REASON)
                logger.info("Created RiskFactor: %s", rf)
            rf.percent = percent
            self.risk_factors.append(rf)
        RiskFactor.objects.normalize_weights()

    def _create_vulnerabilities(self):
        """Create some vulnerabilities according to config.

        Vulnerabilities don't really have many required fields (only 'name').
        """
        self.vulnerabilities = []
        Vulnerability = apps.get_model('bf_opencore', 'Vulnerability')
        vuln_config = self.config_dict.get('vulnerabilities', {})
        for name, config in vuln_config.items():
            percent = config.pop('percent')
            try:
                vuln = Vulnerability.objects.get(name=name)
            except Vulnerability.DoesNotExist:
                vuln = Vulnerability.objects.create(name=name, **config)
                logger.info("Created Vulnerability: %s", vuln)
            vuln.percent = percent
            self.vulnerabilities.append(vuln)

    def _random_macaddr(self, base, range_bits=24):
        """Generate a random MAC address in the given block.

        Result shares the first three octets with base.
        """
        addr = self.np.random.randint(int(base), int(base) + 2**range_bits)
        return netaddr.EUI(addr)

    def _random_ipaddr(self, cidr):
        """Generate a random IP address from a CIDR."""
        intver = self.np.random.randint(cidr.first, cidr.last)
        return netaddr.IPAddress(intver)

    def create_assets(self, nassets, manuf_pct=100,
                      model_pct=100, max_age=0,
                      os_pct=100, owner_pct=100):
        """Create assets according to the weight distribution.

        Returns the number of assets created.
        """
        # too-many-locals is in part a function of @click.  I'm not
        # ready to clean this up now.
        #
        # pylint: disable=too-many-locals,too-many-arguments,too-many-branches

        # generate a weighted distribution and choose randomly from it
        # nassets times
        nwk_weights = [nwk.weight for nwk in self.networks]
        asset_nwks = self.np.random.choice(
            self.networks, nassets, p=nwk_weights)

        # create and store AssetRecord objects corresponding to a list of
        # networks to put them in (asset_nwks is just a list of networks)
        for i, asset_nwk in enumerate(asset_nwks):
            # self.np.random.choice doesn't like choosing from a list of tuples
            manuf, asset_model = random.choice(self.manufacturers)
            macaddr = self._random_macaddr(self.mac_ranges[manuf])
            Asset = apps.get_model('bf_opencore', 'Asset')
            if Asset.objects.filter(mac_address=macaddr).exists():
                # This asset already exists (probably from previous run
                # of mock importer)
                continue

            # optionally, random age for asset
            date_added = timezone.now()
            if max_age:
                age_days = self.np.random.randint(0, max_age)
                date_added -= timedelta(days=age_days)

            asset = Asset(mac_address=str(macaddr),
                                 date_added=date_added)
            asset.ip_address = str(self._random_ipaddr(
                network_cidr(asset_nwk)))

            if self.np.random.uniform(100) < manuf_pct:
                asset.manufacturer = manuf
                if self.np.random.uniform(100) < model_pct:
                    asset.model = asset_model

            if self.np.random.uniform(100) < os_pct:
                asset.os = random.choice(self.oses)

            if self.np.random.uniform(100) < owner_pct:
                asset.owner = random.choice(self.owners)

            asset.save()
            hist_utils.update_change_reason(asset, CHANGE_REASON)

            # Adding AssetRiskFactors
            AssetRiskFactor = apps.get_model('bf_opencore', 'AssetRiskFactor')
            for risk_factor in self.risk_factors:
                if self.np.random.uniform(100) < risk_factor.percent:
                    # Either discrete set of options, numeric, or boolean
                    if risk_factor.scalar and risk_factor.options:
                        value = self.np.random.choice(risk_factor.options)
                    elif risk_factor.scalar:
                        rang = (risk_factor.range_max - risk_factor.range_min)
                        rmin = risk_factor.range_min
                        value = (self.np.random.random_sample() * rang) + rmin
                    else:
                        value = risk_factor.range_max
                        assert value == 1
                    AssetRiskFactor.objects.create(
                        asset=asset, risk_factor=risk_factor,
                        value=value,
                        provenance=CHANGE_REASON)

            # Adding AssetVulnerabilities
            AssetVulnerability = apps.get_model('bf_opencore', 'AssetVulnerability')
            for vulnerability in self.vulnerabilities:
                if self.np.random.uniform(100) < vulnerability.percent:
                    AssetVulnerability.objects.create(
                        asset=asset, vulnerability=vulnerability,
                        provenance=CHANGE_REASON)

            logger.debug('Asset %s (%s) is a %s %s in network %s',
                         i, asset, manuf, asset_model, asset_nwk.name)

            AssetTag = apps.get_model('bf_opencore', 'AssetTag')
            for tag in self.tags:
                if self.np.random.uniform(100) < tag.percent:
                    at = AssetTag(asset=asset, tag=tag,
                                         provenance=CHANGE_REASON)
                    at.save()
                    hist_utils.update_change_reason(at, CHANGE_REASON)

            asset.rescore()

        RiskMetrics = apps.get_model('bf_opencore', 'RiskMetrics')
        RiskMetrics.objects.create_metrics()
        if max_age:
            logger.warning('Not backfilling risk scores.')

        return len(asset_nwks)
