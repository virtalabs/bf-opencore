"""Test autocomplete interface."""

# "redefine outer name" is how pytest fixtures work.

import pytest
from bf_opencore import models


@pytest.fixture
def complete_us(db):
    """Sample assets."""
    mfmods = {
        'Foo': ['One', 'Two', 'Three'],
        'Bar': ['Four', 'Five', 'Six'],
    }

    assets = []
    for manuf, models in mfmods.items():
        for model in models:
            assets.append(models.Asset(manufacturer=manuf, model=model))
    models.Asset.objects.bulk_create(assets)


def test_autocomplete_field(auth_client, complete_us):
    """Test that /autocomplete_field/ returns the right set."""
    assert models.Asset.objects.count() == 6

    manufs = auth_client.get('/api/autocomplete_field/?field=manufacturer')
    assert manufs.status_code == 200
    assert set(manufs.json()) == set(['Foo', 'Bar'])


def test_autocomplete_field_with_constraints(auth_client, complete_us):
    """Test that /autocomplete_field/ respects constraints."""
    assert models.Asset.objects.count() == 6

    manufs = auth_client.get('/api/autocomplete_field/'
                             '?field=model'
                             '&manufacturer=Foo')
    assert manufs.status_code == 200
    assert set(manufs.json()) == set(['One', 'Two', 'Three'])


def test_autocomplete_field_empty(auth_client):
    """Test that /autocomplete_field/ returns empty when it should."""
    assert models.Asset.objects.count() == 0

    manufs = auth_client.get('/api/autocomplete_field/'
                             '?field=manufacturer')
    assert manufs.status_code == 200
    assert manufs.json() == []
