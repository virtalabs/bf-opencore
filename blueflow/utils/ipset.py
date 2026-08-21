"""Translate ip addresses."""

import logging

import netaddr

logger = logging.getLogger(__name__)


def ipset_from_network(network):
    """Return a netaddr.IPSet from a CIDR, glob, or nmap range string.

    >>> ipset_from_network('10.0.1.14')
    IPSet(['10.0.1.14/32'])
    >>> ipset_from_network('10.0.1.14/24')
    IPSet(['10.0.1.0/24'])
    >>> ipset_from_network('10.0.1.14/29')
    IPSet(['10.0.1.8/29'])
    >>> ipset_from_network('10.0.1.*')
    IPSet(['10.0.1.0/24'])
    >>> ipset_from_network('10.0.1.8-23')
    IPSet([])
    >>> ipset_from_network('10.0.2-3.0-255')
    IPSet([])
    >>> ipset_from_network('10.0.2-3.*')
    IPSet([])
    >>> ipset_from_network('10.0.1.14, 10.0.1.15')
    IPSet(['10.0.1.14/31'])
    >>> ipset_from_network('10.0.1.14,10.0.1.15')
    IPSet(['10.0.1.14/31'])
    >>> ipset_from_network('10.0.1.14 10.0.1.15')
    IPSet(['10.0.1.14/31'])
    >>> ipset_from_network('foobar')
    IPSet([])
    >>> ipset_from_network('10.0.1.14 foobar')
    IPSet(['10.0.1.14/32'])
    """
    nwks = network.replace(",", " ").split()  # Split on comma or whitespace
    # "A foolish consistency ..." - it makes most sense to compare on len here
    # pylint: disable=len-as-condition
    if len(nwks) > 1:
        # Comma or whitespace-separated list of network, interpret each
        # of them and join'em all together
        ipset = netaddr.IPSet()
        for nwk in nwks:
            ipset.update(_ipset_from_simple_network(nwk))
        return ipset
    if len(nwks) == 0:
        # No networks in string; return empty IPSet
        return netaddr.IPSet()
    if len(nwks) == 1:
        # One network in string, fall through to the rest of the function
        return _ipset_from_simple_network(nwks[0])

    # Should never get here, but pylint doesn't know this
    return None


def _ipset_from_simple_network(network):
    """Convert a CIDR or glob (not dashed range) to an IPSet.

    >>> _ipset_from_simple_network('10.0.1.14')
    IPSet(['10.0.1.14/32'])
    >>> _ipset_from_simple_network('10.0.1.14/24')
    IPSet(['10.0.1.0/24'])
    >>> _ipset_from_simple_network('10.0.1.14, 10.0.1.15')
    IPSet([])
    """
    if "-" in network:
        logger.error('Nmap ranges like "%s" are not supported.', network)
        return netaddr.IPSet()

    if netaddr.valid_glob(network):
        # This will handle '10.0.1.*' style globs
        return netaddr.IPSet(netaddr.IPGlob(network))

    if netaddr.valid_nmap_range(network):
        # This will handle nmap ranges and CIDRs (and individual hosts)
        return netaddr.IPSet(netaddr.IPNetwork(network).cidr)

    logger.error("Not a valid network: '%s'", network)
    return netaddr.IPSet()
