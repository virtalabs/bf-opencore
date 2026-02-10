"""Test search."""

# Many functions use Model classes which *do* have an 'objects' member

# These errors are endemic to pytest

from bf_opencore import models


def test_free_text_search_manufacturer(auth_client, completables):
    """We can get an asset via its manufacturer with free-text search."""
    candidates = auth_client.get('/api/assets/?search=acme')
    assert candidates.data['count'] == 2


def test_free_text_search_model(auth_client, completables):
    """We can get an asset via its model with free-text search."""
    candidates = auth_client.get('/api/assets/?search=Instant+Tunnel')
    assert candidates.data['count'] == 2


def test_free_text_search_os(auth_client, completables):
    """We can get an asset via its OS with free-text search."""
    candidates = auth_client.get('/api/assets/?search=windows')
    asset = models.Asset.objects.filter(os='Windows 95').first()
    assert candidates.data['count'] == 1
    assert candidates.data['results'][0]['id'] == asset.id


def test_free_text_search_serial_number(auth_client, completables):
    """We can get an asset via its serial number with free-text search."""
    candidates = auth_client.get('/api/assets/?search=wile')
    asset = models.Asset.objects.filter(serial_number='WILE-E-1234').first()
    assert candidates.data['count'] == 1
    assert candidates.data['results'][0]['id'] == asset.id


def test_search_tag(auth_client, completables):
    """We get assets that have a tag attached."""
    asset = models.Asset.objects.get(serial_number='WILE-E-1234')
    tag = models.Tag.objects.get(name="FooTag")
    models.AssetTag.objects.create(tag=tag, asset=asset)
    candidates = auth_client.get('/api/assets/?search=FooTag')
    assert candidates.data['count'] == 1
    assert candidates.data['results'][0]['serial_number'] == 'WILE-E-1234'


def test_search_tag_unattached(auth_client, completables):
    """We don't get assets that don't have the tag attached."""
    candidates = auth_client.get('/api/assets/?search=FooTag')
    assert candidates.data['count'] == 0


def test_search_custom_field_name(auth_client, cfield):
    """Search for the field_name of a custom field.

    The asset 'foo.com' (created in cfield) has a value (it doesn't
    matter what it is) in the custom field 'shinyness'.

    Still, 'shinyness' should not return any results.
    """
    candidates = auth_client.get('/api/assets/?search=shinyness')
    assert candidates.data['count'] == 0


def test_search_custom_field_name_nocust(auth_client, cfield):
    """Search for the field_name of a custom field.

    The asset 'bar.com' (just created) has no value in custom field 'shinyness'

    Still, 'shinyness' should not return any results.
    """
    asset_foo = models.Asset.objects.get(hostname='foo.com')
    asset_foo.delete()
    models.Asset.objects.create(hostname='bar.com')
    candidates = auth_client.get('/api/assets/?search=shinyness')
    assert candidates.data['count'] == 0


def test_search_custom_value(auth_client, cfield):
    """Search for the value of a custom field.

    The asset 'foo.com' has value 'rather dull' in custom field 'shinyness'.
    """
    candidates = auth_client.get('/api/assets/?search=dull')
    assert candidates.data['count'] == 1
    assert candidates.data['results'][0]['hostname'] == 'foo.com'


def test_search_custom_value_badcust(auth_client, cfield):
    """Search for the value of a custom field.

    The asset 'foo.com' has value 'rather dull' in custom field 'shinyness',
    but not 'shinny'.
    (Deliberately misspelled so that it won't match the custom field name!)
    """
    candidates = auth_client.get('/api/assets/?search=shinny')
    assert candidates.data['count'] == 0


def test_search_custom_value_nocust(auth_client, cfield):
    """Search for the value of a custom field.

    No asset has a value in custom field 'shinyness'.
    """
    asset_foo = models.Asset.objects.get(hostname='foo.com')
    asset_foo.delete()
    candidates = auth_client.get('/api/assets/?search=dull')
    assert candidates.data['count'] == 0
