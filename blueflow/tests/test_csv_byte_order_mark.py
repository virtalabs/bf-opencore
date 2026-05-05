"""Test CSV integration."""

from codecs import BOM_UTF8
from pathlib import Path

import pytest

from blueflow.csv import process_csv
from blueflow.models import Asset
from blueflow.tests.utils import write_tempfile

from .test_csv import TestCTX


def test_tempfile_plain():
    """Test that the tempfile writer works as expected."""
    csv_orig = "A,B\n1,2\n"
    filename = write_tempfile(csv_orig)
    with Path(filename).open(encoding="utf-8") as fh:
        csv = fh.read()
    Path(filename).unlink()
    assert csv == csv_orig


def test_tempfile_manual_bom():
    """Insert BOM manually."""
    csv_orig = "A,B\n1,2\n"
    filename = write_tempfile(BOM_UTF8.decode("utf-8") + csv_orig)
    with Path(filename).open(encoding="utf-8") as fh:
        csv = fh.read()
    Path(filename).unlink()
    assert csv[0].encode("utf-8") == BOM_UTF8
    assert csv[0] == BOM_UTF8.decode("utf-8")
    assert csv[1:] == csv_orig


def test_tempfile_auto_bom():
    """Insert BOM with write_tempfile."""
    csv_orig = "A,B\n1,2\n"
    filename = write_tempfile(csv_orig, bom_utf8=True)
    with Path(filename).open(encoding="utf-8") as fh:
        csv = fh.read()
    Path(filename).unlink()
    assert csv[0].encode("utf-8") == BOM_UTF8
    assert csv[0] == BOM_UTF8.decode("utf-8")
    assert csv[1:] == csv_orig


@pytest.mark.usefixtures("_setup_db")
def test_process_csv_without_bom():
    """We can import from a CSV file that doesn't contains the BOM mark."""
    Asset.objects.create(
        manufacturer="Foo",
        ip_address="10.0.0.1",
    )
    field_mapping = {
        "ip_address": "IP",
        "manufacturer": "Manufacturer",
    }
    filename = write_tempfile(
        "IP,Manufacturer\n10.0.0.1,Bar\n",
    )
    asset = Asset.objects.last()
    assert asset.manufacturer == "Foo"

    test_ctx = TestCTX()
    process_csv(
        ctx=test_ctx,
        filename=filename,
        field_mapping=field_mapping,
        require_network_info=False,
        update_only=True,
    )
    Path(filename).unlink()

    asset = Asset.objects.last()
    assert asset.manufacturer == "Bar"


@pytest.mark.usefixtures("_setup_db")
def test_process_csv_with_bom():
    """We can import from a CSV file that contains the BOM mark."""
    Asset.objects.create(
        manufacturer="Foo",
        ip_address="10.0.0.1",
    )
    field_mapping = {
        "ip_address": "IP",
        "manufacturer": "Manufacturer",
    }
    filename = write_tempfile(
        "IP,Manufacturer\n10.0.0.1,Bar\n",
        bom_utf8=True,
    )
    asset = Asset.objects.last()
    assert asset.manufacturer == "Foo"

    test_ctx = TestCTX()
    process_csv(
        ctx=test_ctx,
        filename=filename,
        field_mapping=field_mapping,
        require_network_info=False,
        update_only=True,
    )
    Path(filename).unlink()

    asset = Asset.objects.last()
    assert asset.manufacturer == "Bar"
