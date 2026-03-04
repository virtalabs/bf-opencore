"""Test CSV integration."""

import os

import bf_opencore
import bf_opencore.celery
from bf_opencore.csv import process_csv
from bf_opencore.models import Asset, AssetCustomField, AssetCustomFieldName

from .test_csv import TestCTX, write_tempfile


def test_csv_import_with_custom_field(setup_db, no_nwk_field):
    """We can import from CSV into a custom field."""
    raise NotImplementedError("Connectors have been removed")
    Asset.objects.create(
        manufacturer="Foo",
        model="Bar",
        external_keys={"other_cmms": "ONETWOTHREE"},
    )
    shininess_field_name = AssetCustomFieldName.objects.create(field_name="Shininess")
    field_mapping = {
        "external_keys__other_cmms": "Asset #",
        "asset_custom_fields__Shininess": "How shiny it is",
        "manufacturer": "Manufacturer",
    }
    filename = write_tempfile(
        "Asset #,Manufacturer,How shiny it is\nONETWOTHREE,Different,Very shiny\n",
    )
    asset = Asset.objects.last()
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    assert asset_custom_fields.count() == 0
    bf_opencore.csv.main.apply(
        kwargs={
            "filename": filename,
            "field_mapping": field_mapping,
        }
    )
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert asset_custom_fields.count() == 1

    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_shininess_field = asset_custom_fields.get(field=shininess_field_name)
    asset_shininess = asset_shininess_field.value_text
    assert asset_shininess == "Very shiny"


def test_process_csv_with_custom_field(setup_db):
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
    os.unlink(filename)
    assert asset_custom_fields.count() == 1

    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_shininess_field = asset_custom_fields.get(field=shininess_field_name)
    asset_shininess = asset_shininess_field.value_text
    assert asset_shininess == "Very shiny"


def test_process_csv_with_custom_field_underscores(setup_db):
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
    os.unlink(filename)

    assert asset_custom_fields.count() == 1
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_site_description_field = asset_custom_fields.get(
        field=site_description_field_name
    )
    asset_site_description = asset_site_description_field.value_text
    assert asset_site_description == "Very shiny"


def test_process_csv_with_custom_field_spaces(setup_db):
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
    os.unlink(filename)

    assert asset_custom_fields.count() == 1
    asset_custom_fields = AssetCustomField.objects.filter(asset=asset)
    asset_site_description_field = asset_custom_fields.get(
        field=site_description_field_name
    )
    asset_site_description = asset_site_description_field.value_text
    assert asset_site_description == "Very shiny"
