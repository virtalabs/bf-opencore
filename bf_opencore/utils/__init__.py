
"""Utilities for connectors."""


from enum import Enum, auto
from collections.abc import Iterable
from .fieldmap import FieldMap
from .mssql_client import MSSQLClient
from .func import NullUnlessChanged
from .ipset import ipset_from_network
from .disable_signals import DisableSignals
from .quarters import quarter_start, prev_quarter_start


class password(str):  # pylint: disable=invalid-name
    """Class/type for passwords.

    Works exactly like a regular Python 'str'; is used in the frontend
    (if desired) to indicate that a field is a password and as such
    should not be displayed.
    """


class FileWrapper(str):
    """File wrapper for use with file uploads."""


def iterable(arg):
    """Check if something is really an iterable but not a string."""
    return (isinstance(arg, Iterable) and
            not isinstance(arg, str))


class Created(Enum):
    """Extended Django's "created" flag to include up-to-date."""

    UPDATED = auto()
    CREATED = auto()
    UPTODATE = auto()

    def __bool__(self):
        """Mimic Django behavior in if-statements.

        Return True if created, otherwise False.
        """
        # We need to access private member to get this job done
        # pylint: disable=protected-access,no-member
        return self._value_ == self.CREATED._value_

__all__ = [
    'FieldMap',
    'MSSQLClient',
    'NullUnlessChanged',
    'ipset_from_network',
    'DisableSignals',
    'quarter_start',
    'prev_quarter_start',
    'password',
    'FileWrapper',
    'iterable',
    'Created',
]