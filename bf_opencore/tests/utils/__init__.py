"""test utilities."""

import os


def path_nparent(path, n):
    """Return the n'th parent of path."""
    for _ in range(n):
        path = os.path.dirname(path)
    return path

BLUEFLOW_HOME = path_nparent(__file__, 5)
