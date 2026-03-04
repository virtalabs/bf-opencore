"""Connector test utilities."""

import os

from .mssql_client_mock import configure_mock_mssqlclient


def path_nparent(path, n):
    """Return the n'th parent of path."""
    for dummy in range(n):
        path = os.path.dirname(path)
    return path


BLUEFLOW_HOME = path_nparent(__file__, 5)
