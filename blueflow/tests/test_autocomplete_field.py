"""Test autocomplete interface."""


from blueflow import models
from rest_framework import status


def test_autocomplete_field(auth_client, complete_us):
    """Test that /autocomplete_field/ returns the right set."""
    assert models.Asset.objects.count() == 6  # noqa: PLR2004

    manufs = auth_client.get("/api/autocomplete_field/?field=manufacturer")
    assert manufs.status_code == status.HTTP_200_OK
    assert set(manufs.json()) == {"Foo", "Bar"}


def test_autocomplete_field_with_constraints(auth_client, complete_us):
    """Test that /autocomplete_field/ respects constraints."""
    assert models.Asset.objects.count() == 6  # noqa: PLR2004

    manufs = auth_client.get("/api/autocomplete_field/?field=model&manufacturer=Foo")
    assert manufs.status_code == status.HTTP_200_OK
    assert set(manufs.json()) == {"One", "Two", "Three"}


def test_autocomplete_field_empty(auth_client):
    """Test that /autocomplete_field/ returns empty when it should."""
    assert models.Asset.objects.count() == 0

    manufs = auth_client.get("/api/autocomplete_field/?field=manufacturer")
    assert manufs.status_code == status.HTTP_200_OK
    assert manufs.json() == []
