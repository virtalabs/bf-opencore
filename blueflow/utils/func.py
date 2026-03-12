"""Custom Django functions."""

from django.db.models import Func


class NullUnlessChanged(Func):
    """Custom Django function.

    Based on the Postgres Window function LAG and NULLIF.

    Corresponding Field ('expression') is NULL if unchanged from previous.
    It works by comparing (with NULLIF) the field value against the
    previous value (with LAG, using the default OFFSET of 1.)

    Used in order to detect when a (any) field changed.
    """

    # Apparently I should have overridden __and__, __or__, __rand__, __ror__.
    # pylint: disable=abstract-method

    function = None  # unused, but should be there in most customs.
    template = """
      NULLIF(%(expressions)s,
             LAG(%(expressions)s) OVER (ORDER BY history_date))
    """
