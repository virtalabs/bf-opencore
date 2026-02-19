
"""Test that mock connector creates assets without crashing."""

import pytest
try:
    import numpy as np
except ImportError:
    np = None

from bf_opencore.connectors import mock
from bf_opencore.connectors.mock.mock import MockPopulation

from bf_opencore.connectors.management.commands.create_connectors import create_connectors


# pylint: disable=line-too-long, unused-argument
@pytest.mark.slow
@pytest.mark.skipif(np is None, reason="Missing numpy")
def test_create_mock_assets(db):
    """Test that creates a failure when rescoring an asset.

    Set Breakpoints:
    b app/connectors/mock/mock.py:267
    b app/blueflow/models/asset.py:451
    """
    popfile = mock.DEFAULT_POPFILE
    nassets = 100

    create_connectors()

    np.random.seed(8)
    pop = MockPopulation.from_file(popfile)
    # import pdb ; pdb.set_trace()
    dummy_created = pop.create_assets(nassets)
