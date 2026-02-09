# Copyright (C) 2017-2019 Virta Laboratories, Inc.  All rights reserved.

"""Utils that are useful for many apps."""

import collections
from enum import Enum, auto

from .ipset import ipset_from_network
from .disable_signals import DisableSignals
from .func import NullUnlessChanged
from .quarters import quarter_start, prev_quarter_start


def iterable(arg):
    """Check if something is really an iterable but not a string."""
    return (isinstance(arg, collections.abc.Iterable) and
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
