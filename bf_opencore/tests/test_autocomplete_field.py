"""Test autocomplete interface."""

from bf_opencore import models


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
