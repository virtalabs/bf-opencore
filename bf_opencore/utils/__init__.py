
"""Utilities for connectors."""

from .fieldmap import FieldMap
from .mssql_client import MSSQLClient


class password(str):  # pylint: disable=invalid-name
    """Class/type for passwords.

    Works exactly like a regular Python 'str'; is used in the frontend
    (if desired) to indicate that a field is a password and as such
    should not be displayed.
    """


class FileWrapper(str):
    """File wrapper for use with file uploads."""
