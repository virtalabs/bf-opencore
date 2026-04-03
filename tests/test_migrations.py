"""Project-level migration tests.

PostgreSQL required via DATABASE_URL in test settings.
"""

import pytest


def test_blueflow_initial_migration_applies(migrator):
    """Ensure blueflow initial migration applies (project-level migration sanity)."""
    # Before: no blueflow tables
    old_state = migrator.apply_initial_migration(("blueflow", None))
    with pytest.raises(LookupError):
        old_state.apps.get_model("blueflow", "Asset")

    # Apply initial migration
    new_state = migrator.apply_tested_migration(("blueflow", "0001_initial"))
    Asset = new_state.apps.get_model("blueflow", "Asset")
    assert Asset is not None
    assert hasattr(Asset, "objects")
