
"""Test CSV connector."""

import os
import bf_opencore.connectors.celery
from bf_opencore.bf_opencore.models import Asset, ConnectorTask
# TODO: we should NOT be doing setup like this
from .test_csv import write_tempfile, setup_db, no_nwk_field
from bf_opencore import connectors


def test_sync_match_on_string_key_id_other_cmms(setup_db, no_nwk_field):
    """Looking up an asset by its arbitrary PK finds the right asset."""
    Asset.objects.create(
        manufacturer='Foo',
        model='Bar',
        external_keys={'other_cmms': 'ONETWOTHREE'},
    )
    field_mapping = {
        'external_keys__other_cmms': 'Asset #',
        'manufacturer': 'Manufacturer',
        'ip_address': 'IP',
    }
    filename = write_tempfile(
        "Asset #,IP,Manufacturer\n"
        "ONETWOTHREE,1.2.3.4,Different\n"
    )
    asset = Asset.objects.last()
    assert asset.manufacturer == "Foo"
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()
    assert asset.manufacturer == "Different"


def test_match_on_ex_key_bad_ip(setup_db, no_nwk_field):
    """Match existing asset with ex key, but where incoming IP is bad."""
    Asset.objects.create(
        manufacturer='Foo',
        external_keys={'other_cmms': 'ONETWOTHREE'},
    )
    field_mapping = {
        'external_keys__other_cmms': 'Asset #',
        'manufacturer': 'Manufacturer',
        'ip_address': 'IP',
    }
    filename = write_tempfile(
        "Asset #,IP,Manufacturer\n"
        "ONETWOTHREE,b0d_ip,Different\n"
    )
    connectors.csv.main.apply(
        kwargs={'filename': filename, 'field_mapping': field_mapping})
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()
    assert asset.manufacturer == "Different"


def test_match_on_ex_key_bad_mac(setup_db, no_nwk_field):
    """Match existing asset with ex key, but where incoming MAC is bad."""
    Asset.objects.create(
        manufacturer='Foo',
        external_keys={'other_cmms': 'ONETWOTHREE'},
    )
    field_mapping = {
        'external_keys__other_cmms': 'Asset #',
        'manufacturer': 'Manufacturer',
        'mac_address': 'MAC',
    }
    filename = write_tempfile(
        "Asset #,MAC,Manufacturer\n"
        "ONETWOTHREE,b0d_mac,Different\n"
    )
    connectors.csv.main.apply(
        kwargs={'filename': filename, 'field_mapping': field_mapping})
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()
    assert asset.manufacturer == "Different"


def test_match_on_ex_key_no_ip_mac(setup_db, no_nwk_field):
    """Match existing asset with ex key, but with no IP/MAC in field map.

    This *should* work.  It corresponds roughly to
    test_asset_match_truth_table.py::test_update_or_create_case_19b
    """
    Asset.objects.create(
        manufacturer='Foo',
        external_keys={'other_cmms': 'ONETWOTHREE'},
    )
    field_mapping = {
        'external_keys__other_cmms': 'Asset #',
        'manufacturer': 'Manufacturer',
    }
    filename = write_tempfile(
        "Asset #,Manufacturer\n"
        "ONETWOTHREE,Different\n"
    )
    connectors.csv.main.apply(
        kwargs={'filename': filename, 'field_mapping': field_mapping})
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()
    assert asset.manufacturer == "Different"


def test_create_with_ex_key_no_ip_mac(setup_db, no_nwk_field):
    """Create new asset with ex key, but with no IP/MAC in field map.

    This *should* work.  It corresponds roughly to
    test_asset_match_truth_table.py::test_update_or_create_case_19b
    """
    assert Asset.objects.count() == 0
    field_mapping = {
        'external_keys__other_cmms': 'Asset #',
        'manufacturer': 'Manufacturer',
    }
    filename = write_tempfile(
        "Asset #,Manufacturer\n"
        "ONETWOTHREE,Different\n"
    )
    connectors.csv.main.apply(
        kwargs={'filename': filename, 'field_mapping': field_mapping})
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()
    assert asset.manufacturer == "Different"


def test_create_with_empty_ex_key_ip_mac(setup_db, no_nwk_field):
    """Try create new asset with empty ex key and no IP/MAC in field map.

    This *should* work.  It corresponds roughly to
    test_asset_match_truth_table.py::test_update_or_create_case_19b
    """
    assert Asset.objects.count() == 0
    field_mapping = {
        'external_keys__other_cmms': 'Asset #',
        'manufacturer': 'Manufacturer',
    }
    filename = write_tempfile(
        "Asset #,Manufacturer\n"
        ",Different\n"
    )
    connectors.csv.main.apply(
        kwargs={'filename': filename, 'field_mapping': field_mapping})
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 0


def test_create_without_ex_key_ip_mac(setup_db, no_nwk_field):
    """Try create new asset without ex key nor IP/MAC in field map.

    This *should* work.  It corresponds roughly to
    test_asset_match_truth_table.py::test_update_or_create_case_19b
    """
    assert Asset.objects.count() == 0
    field_mapping = {
        'manufacturer': 'Manufacturer',
    }
    filename = write_tempfile(
        "Manufacturer\n"
        "Different\n"
    )
    connectors.csv.main.apply(
        kwargs={'filename': filename, 'field_mapping': field_mapping})
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Failed'  # This fails "earlier" than the one above
    assert Asset.objects.count() == 0
