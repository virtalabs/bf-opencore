"""Test CSV integration."""

from pathlib import Path

import pytest

from blueflow.csv import process_csv
from blueflow.models import Asset, AssetCustomField, AssetCustomFieldName
from blueflow.tests.utils import write_tempfile

from .test_csv import TestCTX


@pytest.mark.usefixtures("_setup_db")
def test_process_csv_with_custom_field():
    """We can import from CSV into a custom field.

    Similar to test above but lower level (more unit test)
    -- i.e., avoiding Celery tasks.
    """
    Asset.objects.create(
        manufacturer="Foo",
        model="Bar",
        external_keys={"other_cmms": "ONETWOTHREE"},
    )
    shininess_field_name = AssetCustomFieldName.objects.create(field_name="Shininess")
    field_mapping = {
        "external_keys__other_cmms": "Asset #",
        "asset_custom_fields__Shininess": "Shininess",
        "manufacturer": "Manufacturer",
    }
    filename = write_tempfile(
        "Asset #,Manufacturer,Shininess\nONETWOTHREE,Different,Very shiny\n",
    )
    asset = Asset.objects.last()
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    assert asset_custom_fields.count() == 0

    test_ctx = TestCTX()
    process_csv(
        ctx=test_ctx,
        filename=filename,
        field_mapping=field_mapping,
        require_network_info=False,
        update_only=True,
    )
    Path(filename).unlink()
    assert asset_custom_fields.count() == 1

    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_shininess_field = asset_custom_fields.get(field=shininess_field_name)
    asset_shininess = asset_shininess_field.value_text
    assert asset_shininess == "Very shiny"


@pytest.mark.usefixtures("_setup_db")
def test_process_csv_with_custom_field_underscores():
    """We can import from CSV into a custom field that contains underscores."""
    Asset.objects.create(
        manufacturer="Foo",
        model="Bar",
        external_keys={"other_cmms": "ONETWOTHREE"},
    )
    site_description_field_name = AssetCustomFieldName.objects.create(
        field_name="site_description"
    )
    field_mapping = {
        "external_keys__other_cmms": "Asset #",
        "asset_custom_fields__site_description": "SiteDescription",
        "manufacturer": "Manufacturer",
    }
    filename = write_tempfile(
        "Asset #,Manufacturer,SiteDescription\nONETWOTHREE,Different,Very shiny\n",
    )
    asset = Asset.objects.last()
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    assert asset_custom_fields.count() == 0

    test_ctx = TestCTX()
    process_csv(
        ctx=test_ctx,
        filename=filename,
        field_mapping=field_mapping,
        require_network_info=False,
        update_only=True,
    )
    Path(filename).unlink()

    assert asset_custom_fields.count() == 1
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_site_description_field = asset_custom_fields.get(
        field=site_description_field_name
    )
    asset_site_description = asset_site_description_field.value_text
    assert asset_site_description == "Very shiny"


@pytest.mark.usefixtures("_setup_db")
def test_process_csv_with_custom_field_spaces():
    """We can import from CSV into a custom field that contains spaces."""
    Asset.objects.create(
        manufacturer="Foo",
        model="Bar",
        external_keys={"other_cmms": "ONETWOTHREE"},
    )
    site_description_field_name = AssetCustomFieldName.objects.create(
        field_name="Site Description"
    )
    field_mapping = {
        "external_keys__other_cmms": "Asset #",
        "asset_custom_fields__Site_Description": "SiteDescription",
        "manufacturer": "Manufacturer",
    }
    filename = write_tempfile(
        "Asset #,Manufacturer,SiteDescription\nONETWOTHREE,Different,Very shiny\n",
    )
    asset = Asset.objects.last()
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    assert asset_custom_fields.count() == 0

    test_ctx = TestCTX()
    process_csv(
        ctx=test_ctx,
        filename=filename,
        field_mapping=field_mapping,
        require_network_info=False,
        update_only=True,
    )
    Path(filename).unlink()

    assert asset_custom_fields.count() == 1
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_site_description_field = asset_custom_fields.get(
        field=site_description_field_name
    )
    asset_site_description = asset_site_description_field.value_text
    assert asset_site_description == "Very shiny"
