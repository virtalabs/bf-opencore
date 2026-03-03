"""Project-level migration tests (PostgreSQL required via DATABASE_URL in test settings)."""

import pytest


@pytest.mark.django_db
def test_bf_opencore_initial_migration_applies(migrator):
    """Ensure bf_opencore initial migration applies (project-level migration sanity)."""
    # Before: no bf_opencore tables
    old_state = migrator.apply_initial_migration(("bf_opencore", None))
    with pytest.raises(LookupError):
        old_state.apps.get_model("bf_opencore", "Asset")

    # Apply initial migration
    new_state = migrator.apply_tested_migration(("bf_opencore", "0001_initial"))
    Asset = new_state.apps.get_model("bf_opencore", "Asset")
    assert Asset is not None
    assert hasattr(Asset, "objects")
