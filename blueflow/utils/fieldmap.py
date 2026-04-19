"""Map BlueFlow ORM fields to external database column names.

For example, the names of the fields (AKA table column names) in a customer's
inventory database are probably different that the names of the columns in
BlueFlow's tables (its internal ORM).
"""

import ipaddress

import netaddr
from django.apps import apps

from blueflow.exceptions import IntegrationTaskError

EUI48_VERSION = 48
IPV4_VERSION = 4
BROADCAST_OCTET = 255


class FieldMap:
    """Dictionary with a layer of indirection for the keys.

    Example:
    data = {
        "MAC_2": "",
        "MAC_1": "00:00:00:00:00:00",
    }
    keymap = {
        'mac_address': [
            'MAC_1',
            'MAC_2',
        },
    indirect = FieldMap(data, keymap)
    assert indirect['mac_address'] == "00:00:00:00:00:00"

    """

    def __init__(self, data, keymap):
        """Create a new FieldMap from two Dictionaries.

        - data is dictionary of external_key -> value pairs
        - keymap maps an orm_key to an external_key or [list of external_key]

        Every key from the keymap is included.  Any key that does not map
        will raise a IntegrationTaskError.  Some data items will be
        ignored.

        Lookups return the first value that is not None or whitespace.  If all
        lookups contain None or whitespace, returns None.
        """
        self._data = data
        self._keymap = keymap
        self._joined = {}
        self.normalize_keymap()  # Modifies self._keymap
        self.validate()
        self.forward_map_all()  # Modified self._joined

    def normalize_keymap(self):
        """Coerce self._keymap to a dict where each value is a list.

        Example:
        self._keymap before:
        {
            'mac_address': ['MAC_1', 'MAC_2'],
            'ip_address': 'IP',
        }
        self._keymap after:
        {
            'mac_address': ['MAC_1', 'MAC_2'],
            'ip_address': ['IP'],
        }

        """
        new_keymap = {}  # Can't change a dict while iterating over it, so copy
        for key, value in self._keymap.items():
            if isinstance(value, str):
                # Convert strings to a list containing one item
                new_keymap[key] = [value]
            else:
                # Ensure it's an iterable by coercing to list
                new_keymap[key] = list(value)
        self._keymap = new_keymap

    @staticmethod
    def validate_orm_keys(keymap):
        """Validate keymap keys against Asset fields.

        This method exists so that we can have fail-fast behavior.
        """
        Asset = apps.get_model("blueflow", "Asset")
        for orm_key in keymap.keys():
            if not Asset.is_valid_field_name(orm_key):
                raise IntegrationTaskError(
                    f"'{orm_key}' key in FieldMap does not match any Asset field",
                )

    @staticmethod
    def unique_keymap_values(keymap):
        """Return a unique list of values from a keymap.

        This method exists for the database to use later to speed up SQL
        queries.  It will only query for column names mentioned in a
        field mapping.
        """
        output = set()
        for value in keymap.values():
            if isinstance(value, str):
                output.add(value)
            else:
                output.update(list(value))
        return output

    def validate(self):
        """Validate ORM keys and external keys.

        Raises IntegrationTaskError on mismatch.

        A longer explanation: Every keymap key (an ORM key) must be a valid
        Asset field.  Every keymap value (an external database key) must be a
        string.  Furthermore, every keymap value must map to a key in the
        external data.
        """
        # Every keymap key must be a valid Asset field
        FieldMap.validate_orm_keys(self._keymap)

        for extkey_list in self._keymap.values():
            for extkey in extkey_list:
                # External keys must be strings
                if not isinstance(extkey, str):
                    raise IntegrationTaskError(
                        f"keymap value '{extkey}': "
                        f"Expected a string.  Got {type(extkey).__name__}.",
                    )

                # External keys must map to a data key
                if extkey not in self._data.keys():
                    raise IntegrationTaskError(
                        f"keymap value '{extkey}' "
                        + "does not map to a data key '{}'".format(
                            ", ".join(self._data.keys())
                        ),
                    )

    def forward_map_all(self):
        """Map every key in the keymap to a value from the data.

        If any key in the keymap that does not map to a data value, raise a
        IntegrationTaskError.  Note that this means some data values may be
        ignored.
        """
        self._joined = {}
        for orm_key in self._keymap.keys():
            self._joined[orm_key] = self.forward_map(orm_key)

    def forward_map(self, orm_key):
        """Map ORM key to external data value.

        Assumes that every key in the keymap successfully maps to a data value.
        Successful mapping was already checked by self.validate() in the
        constructor.

        A note about naming.  The keymap maps ORM keys (orm_key) to external
        keys (extkey).  The external keys are database column names in an
        external data source (e.g., AIMS, TMS).  We are interested in external
        data values access by ORM key names.
        """
        for extkey in self._keymap[orm_key]:
            value = self._data[extkey]

            # Strip whitespace
            if isinstance(value, str):
                value = value.strip()

            # Ignore null values
            if value is None:
                continue

            # Ignore empty string values
            if value == "":
                continue

            # Ignore invalid MAC addresses and clean up valid MAC addresses
            if orm_key == "mac_address":
                clean_mac = valid_mac_address(value)
                if clean_mac:
                    value = clean_mac
                else:
                    continue

            # Ignore invalid IP addresses and clean up valid IP addresses
            if orm_key == "ip_address":
                clean_ip = valid_ip_address(value)
                if clean_ip:
                    value = clean_ip
                else:
                    continue

            # Ignore anything that Django's ORM type system doesn't like
            Asset = apps.get_model("blueflow", "Asset")
            if not Asset.is_valid_field_value(orm_key, value):
                continue

            # Must be a valid value
            return value

        # Couldn't find a valid value after trying every keymap target value
        return None

    def todict(self):
        """Return a join of data and keymap."""
        return self._joined

    def __getitem__(self, orm_key):
        """Return the mapped value of an internal field name.

        Raise IntegrationTaskError if not found.
        """
        try:
            return self._joined[orm_key]
        except KeyError:
            raise IntegrationTaskError(
                f"orm key '{orm_key}' not in FieldMap",
            )

    def __repr__(self):
        """Print full mapping in dict form."""
        return self._joined.__repr__()

    def __str__(self):
        """Print full mapping in dict form."""
        return self.__repr__()


def valid_mac_address(mac_address):
    """Return cleaned MAC string if mac_address is "reasonable", otherwise None.

    "Reasonable" means a valid EUI 48 address and not an integer.
    """
    if mac_address is None:
        return None

    # Clean up whitespace
    if isinstance(mac_address, str):
        mac_address = mac_address.strip()

    try:
        dummy = int(mac_address)
    except ValueError:
        pass
    else:
        # Don't accept pure integers.  The netaddr.EUI() function would
        # accept pure integers as valid MAC addresses, but we don't.
        return None

    # Parse MAC address using netaddr library
    try:
        mac = netaddr.EUI(mac_address)
    except (netaddr.AddrFormatError, IndexError):
        return None

    # Only accept EUI 48 MACs
    if mac.version != EUI48_VERSION:
        return None

    # All checks pass.  Format as "00:01:02:03:04:0f"
    mac.dialect = netaddr.mac_unix_expanded
    return mac


def valid_ip_address(ip_address):
    """Return cleaned IP string if ip "reasonable", otherwise return None.

    "Reasonable" means likely to correspond to a real thing on a real
    network, i.e., doesn't violate common numbering rules.

    Helpful reference about IP addresses:
    http://www.comptechdoc.org/independent/networking/guide/netaddressing.html
    """
    # This function is designed to be easy to read
    # pylint: disable=too-many-return-statements,too-many-branches
    if ip_address is None:
        return None

    # Clean up whitespace
    if isinstance(ip_address, str):
        ip_address = ip_address.strip()

    # Don't accept pure integers.  The ip_interface() function would
    # accept pure integers as valid IP addresses, but we don't.
    try:
        dummy = int(ip_address)
    except ValueError:
        pass
    else:
        return None

    # Parse IP address using ipaddress library
    try:
        iface = ipaddress.ip_interface(ip_address)
    except ValueError:
        return None

    # Don't accept ipv6 addresses
    if iface.ip.version != IPV4_VERSION:
        return None

    # When setting addresses on a network, remember there can be no host
    # address of 0 (no host address bits set).
    # Reference:
    # http://www.comptechdoc.org/independent/networking/guide/netaddressing.html
    if iface.ip.packed[0] == 0 or iface.ip.packed[3] == 0:
        return None

    # Don't accept broadcast addresses
    if BROADCAST_OCTET in iface.ip.packed:
        return None

    # Don't accept multicast addresses
    if iface.ip.is_multicast:
        return None

    # Don't accept loopback addresses
    if iface.ip.is_loopback:
        return None

    # Don't accept Microsoft private addresses
    if list(iface.ip.packed[:2]) == [169, 254]:
        return None

    # This is reserved for hosts that don't know their address and use BOOTP or
    # DHCP protocols to determine their addresses.
    if str(iface.network) == "0.0.0.0/0":
        return None

    # All checks pass
    return iface.ip
