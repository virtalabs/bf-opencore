"""Utility functions for dealing with hostnames and IP addresses."""

import ipaddress
import re

import netaddr

MAX_HOSTNAME_LENGTH = 253
IPV4_VERSION = 4


def hostname_ok(hostname):
    """Check whether a string is a valid hostname or IP address.

    Valid in the sense of RFC 3696:
      https://tools.ietf.org/html/rfc3696#section-2
    """
    # adapted from SO:
    # https://stackoverflow.com/questions/2532053/validate-a-hostname-string
    hostname = hostname.removesuffix(".")
    if len(hostname) > MAX_HOSTNAME_LENGTH:
        return False

    chunks = hostname.split(".")

    # disallow numeric TLD
    if re.match(r"[0-9]+$", chunks[-1]):
        return False
    chunk_ok = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)

    return all(chunk_ok.match(chunk) for chunk in chunks)


def ip_address_ok(ipaddr):
    """Check whether an IPv4 address is in sane-looking dotted-quad form.

    Funny business like "23.001.3.4" may be "valid" in the strictest sense, but
    not "sane" in a reasonable sense, so this check boils down to whether a
    stringified validated IPv4 address is any different from the provided
    address.
    """
    try:
        ipa = ipaddress.ip_address(ipaddr)
    except ValueError:
        return False
    if ipa.version != IPV4_VERSION:
        return False
    return str(ipa) == ipaddr


def cidr_ok(cidr):
    """Check whether a CIDR is in sane-looking format."""
    return netaddr.valid_nmap_range(cidr)
