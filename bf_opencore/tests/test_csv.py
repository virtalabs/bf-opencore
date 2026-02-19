
"""Test CSV connector."""

import os
import tempfile
import pytest
import django.core.management
import bf_opencore.connectors.celery
from bf_opencore.bf_opencore.models import Asset, Connector, ConnectorTask
from bf_opencore import connectors

@pytest.fixture()
def setup_db(db):
    """Create connector objects."""
    # ConnectorTask objects are linked to Connector objects with a foreign key
    # relationship.  We need those objects to be available.
    django.core.management.call_command('create_connectors')

    # First enable Connector that's disabled by default
    connector = Connector.objects.get(id="csv")
    connector.enabled = True
    connector.save()


@pytest.fixture()
def no_nwk_field():
    """Configure the CSV connector to not require network field."""
    connector = Connector.objects.get(id="csv")
    connector.settings["require_network_info"] = False
    connector.save()


class TestCTX():
    """Dummy class for testing

    Sometimes we want to test 'process_csv' directly, and it needs a
    context with some methods.
    """

    # pylint: disable=too-few-public-methods

    class TestConnectorTask():
        """See parent class docstring."""
        display_name = 'TestConnectorTask'

        def inc_progress(self):
            pass

        def error(self, *args, **kwargs):
            pass

        def print(self, *args, **kwargs):
            pass

    ct = TestConnectorTask()


def write_tempfile(text, bom_utf8=False):
    """Write text (ostensibly, CSV) to a temp file and return the filename."""
    csvfd, filename = tempfile.mkstemp(suffix='.csv')
    if bom_utf8:
        # The 'utf-8-sig' special encoding inserts the byte order mark
        # '0xef, 0xbb, 0xdf' at the beginning of the file (or strips it
        # off, if it's there when reading.)
        # NOTE: in general it is *discouraged* to use this BOM.  We use
        # it here only to test that we're robust against it if it is in
        # a file we come across.
        #
        # https://docs.python.org/3/library/codecs.html#encodings-and-unicode
        encoding = 'utf-8-sig'
    else:
        encoding = None
    with open(csvfd, 'w', encoding=encoding) as fh:
        fh.write(text)
    return filename


def test_csv_simple(setup_db):
    """
    Run a connector task and verify that it was connected to the DB.
    This will implicitely verify that the Celery signals correctly created
    and associated with a ConnectorTask database object.  That means there will
    be exactly one ConnectorTask object in the database.
    """
    # It would be really confusing to break up a CSV line on to multiple lines
    # pylint: disable=line-too-long
    field_mapping = {
        'serial_number': 'Serial',
        'mac_address': 'MAC',
        'ip_address': 'IP',
        'manufacturer': 'Manufacturer',
        'model': 'Model',
    }
    filename = write_tempfile(
        "Manufacturer,Model,IP,MAC,Serial,other\n"
        "Hospira,Plum A+,10.10.0.13,01:00:00:00:00:13,a013,This thing is totally broken\n"
        "Alaris,8100,192.168.0.1,01:00:00:00:00:01,a001,Last serviced by Ben\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.filter(mac_address="01:00:00:00:00:13").exists()
    assert Asset.objects.filter(mac_address="01:00:00:00:00:01").exists()


def test_csv_non_default_field_mapping(setup_db):
    """
    Run a connector task and verify that it was connected to the DB.
    This will implicitely verify that the Celery signals correctly created
    and associated with a ConnectorTask database object.  That means there will
    be exactly one ConnectorTask object in the database.
    """
    # It would be really confusing to break up a CSV line on to multiple lines
    # pylint: disable=line-too-long
    field_mapping = {
        'serial_number': 'MySerial',
        'mac_address': 'MyMAC',
        'ip_address': 'MyIP',
        'manufacturer': 'MyManufacturer',
        'model': 'MyModel',
    }
    filename = write_tempfile(
        "MyManufacturer,MyModel,MyIP,MyMAC,MySerial,Mother\n"
        "Hospira,Plum A+,10.10.0.13,01:00:00:00:00:13,a013,This thing is totally broken\n"
        "Alaris,8100,192.168.0.1,01:00:00:00:00:01,a001,Last serviced by Ben\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 2
    assert Asset.objects.filter(mac_address="01:00:00:00:00:13").exists()
    assert Asset.objects.filter(mac_address="01:00:00:00:00:01").exists()


def test_no_ip_or_mac(setup_db):
    """Do not import assets with neither IP nor MAC address."""
    # It would be really confusing to break up a CSV line on to multiple lines
    # pylint: disable=line-too-long
    field_mapping = {
        'mac_address': 'MyMAC',
        'ip_address': 'MyIP',
    }
    filename = write_tempfile(
        "MyIP,MyMAC\n"
        ",,\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 0


def test_bad_mac(setup_db):
    """Test that a weird MAC address precludes saving asset."""
    # pylint: disable=unused-argument
    field_mapping = {
        'external_keys__tms': 'AssetNumber',
        'mac_address': 'MACAddress',
    }
    filename = write_tempfile(
        "AssetNumber,MACAddress\n"
        "126,72.18.10.62\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 0


def test_bad_ip(setup_db):
    """Test that a bad IP address precludes saving asset."""
    # pylint: disable=unused-argument
    field_mapping = {
        'external_keys__tms': 'AssetNumber',
        'ip_address': 'IP1',
    }
    filename = write_tempfile(
        "AssetNumber,IP1\n"
        "126,192.168.0.345\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    assert Asset.objects.count() == 0


def test_to_asset_model_ok(setup_db):
    """Mapping to Asset model fields works."""
    field_mapping = {
        'manufacturer': ['Manoof'],
        'model': 'Model',
        'ip_address': 'LAN 1 IP',
    }
    filename = write_tempfile(
        "Model,AssetNumber,LAN 1 IP,Manoof\n"
        "X4000,1,10.0.0.1,FooCorp\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    asset = Asset.objects.last()
    assert asset.manufacturer == 'FooCorp'
    assert asset.model == 'X4000'


def test_to_asset_model_bad_invalidated1(setup_db):
    """Field that doesn't exist in Asset unwelcome in field mapping."""
    field_mapping = {
        'manufacturer': ['Manoof'],
        'nonexistent_field': 'Hi there',
    }
    filename = write_tempfile(
        "AssetNumber,Manoof\n"
        "124,FooCorp\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Failed'
    assert "'nonexistent_field' key in FieldMap" in ct.stderr


def test_to_asset_model_bad_invalidated2(setup_db):
    """Field that doesn't exist in Asset unwelcome in field mapping."""
    field_mapping = {
        'manufacturer': ['M'],
    }
    filename = write_tempfile(
        "AssetNumber,Manoof\n"
        "124,FooCorp\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Failed'
    assert "keymap value 'M' does not map" in ct.stderr


def test_fail_validation(setup_db):
    """Bad field values should fail validation upon conversion."""
    field_mapping = {
        'mac_address': 'MACAddress',
        'external_keys__tms': 'AssetNumber',
    }
    filename = write_tempfile(
        "AssetNumber,MACAddress\n"
        "1,0:1:2:3:4:5\n"
        "2,hamburger\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'

    # Import the asset when when MAC address is valid
    asset = Asset.objects.get(mac_address="0:1:2:3:4:5")
    assert asset.external_keys['tms'] == '1'

    # Don't import when the MAC is invalid
    assert not Asset.objects.filter(external_keys__tms="2").exists()


def test_sync_match_on_integer_key_id(setup_db):
    """Looking up an asset by its TMS Key ID finds the right asset."""
    Asset.objects.create(
        manufacturer='Foo',
        model='Bar',
        external_keys={'tms': '123'},
    )
    field_mapping = {
        'manufacturer': 'Manufacturer',
        'ip_address': 'LAN 1 IP',
        'external_keys__tms': 'AssetNumber',
    }
    filename = write_tempfile(
        "AssetNumber,LAN 1 IP,Manufacturer\n"
        "123,10.0.0.1,Different\n"
    )
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


def test_sync_match_on_string_key_id(setup_db):
    """Looking up an asset by its (string) TMS PK finds the right asset."""
    Asset.objects.create(
        manufacturer='Foo',
        model='Bar',
        external_keys={'tms': 'ONETWOTHREE'},
    )
    field_mapping = {
        'external_keys__tms': 'Asset #',
        'manufacturer': 'Manufacturer',
        'ip_address': 'LAN 1 IP',
    }
    filename = write_tempfile(
        "Asset #,LAN 1 IP,Manufacturer\n"
        "ONETWOTHREE,10.0.0.1,Different\n"
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


def test_risk_score_simple(setup_db):
    """Looking up an asset by its (string) TMS PK finds the right asset."""
    field_mapping = {
        'mac_address': 'MAC',
        'asset_risk_factors__tms': 'RISK',
    }
    filename = write_tempfile(
        "MAC,RISK\n"
        "11:22:33:44:55:66,5.7\n"
    )

    # Run CSV connector
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)

    # Check ConnectorTask database entry of recently run connector
    ct = ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert ct.stderr == ""

    # Check Asset created by connector
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()

    # Check AssetRiskFactor created by connector
    assert asset.asset_risk_factors.count() == 1
    arf = asset.get_risk_factor("tms")
    assert arf.value == 5.7


def test_risk_score_invalid(setup_db):
    """Non-numeric string for risk score."""
    field_mapping = {
        'mac_address': 'MAC',
        'asset_risk_factors__tms': 'RISK',
    }
    filename = write_tempfile(
        "MAC,RISK\n"
        "11:22:33:44:55:66,five point seven\n"
    )

    # Run CSV connector
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)

    # Check ConnectorTask database entry of recently run connector
    ct = ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert ct.stderr == ""

    # Check Asset created by connector.  The asset is created, and an error
    # occurs when adding a risk factor to the asset.
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()

    # Risk is coerced to 0
    assert asset.asset_risk_factors.count() == 1
    arf = asset.get_risk_factor("tms")
    assert arf.value == 0.0


def test_risk_score_none(setup_db):
    """Field mappping fails to find a value for risk score."""
    field_mapping = {
        'mac_address': 'MAC',
        'asset_risk_factors__tms': 'RISK',
    }
    filename = write_tempfile(
        "MAC,RISK\n"
        "11:22:33:44:55:66,\n"  # RISK value is empty string
    )

    # Run CSV connector
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)

    # Check ConnectorTask database entry of recently run connector
    ct = ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert "" in ct.stderr

    # Check Asset created by connector
    assert Asset.objects.count() == 1
    asset = Asset.objects.last()

    # Risk is coerced to 0
    assert asset.asset_risk_factors.count() == 1
    arf = asset.get_risk_factor("tms")
    assert arf.value == 0.0


def test_category(setup_db):
    """Test import to the category field through a field mapping."""
    # It would be really confusing to break up a CSV line on to multiple lines
    # pylint: disable=line-too-long
    field_mapping = {
        'mac_address': 'MAC',
        'category': 'Category',
    }
    filename = write_tempfile(
        "MAC,Category\n"
        "11:22:33:44:55:66,Infusion Pump\n"
    )
    connectors.csv.main.apply(kwargs={
        'filename': filename,
        'field_mapping': field_mapping,
    })
    os.unlink(filename)
    ct = ConnectorTask.objects.get()
    assert ct.status == 'Success'
    asset = Asset.objects.get(mac_address="11:22:33:44:55:66")
    assert asset.category == "Infusion Pump"
