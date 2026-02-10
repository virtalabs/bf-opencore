"""Supplemental module.

In order to test that logging works with imported modules, we need a
module to import.
"""

import logging

logger = logging.getLogger(__name__)


def advanced_math(x, y):
    """Add two numbers."""
    logger.info("Math fun")
    logger.debug("Will do advanced math with %s and %s", x, y)
    z = x + y
    return z
