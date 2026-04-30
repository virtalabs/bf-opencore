"""Tests for the ``zeek_ingest`` management command and the sidecar module."""

import json
from pathlib import Path

import pytest
from django.core.management import call_command

from blueflow import models
from blueflow.zeek.sidecar import payloads_from_logdir


def _write_logs(tmp_path: Path, hl7_lines: list[dict], conn_lines: list[dict]) -> Path:
    """Materialize hl7.log + conn.log in tmp_path. Return the directory."""
    (tmp_path / "hl7.log").write_text(
        "\n".join(json.dumps(line) for line in hl7_lines) + "\n",
    )
    (tmp_path / "conn.log").write_text(
        "\n".join(json.dumps(line) for line in conn_lines) + "\n",
    )
    return tmp_path


HL7_ENTRY = {
    "ts": 1234567890.0,
    "uid": "CabcXY",
    "id.orig_h": "10.0.0.155",
    "id.orig_p": 54321,
    "id.resp_h": "10.0.0.1",
    "id.resp_p": 2575,
    "is_orig": True,
    "sending_app": "Infuse-O-Matic",
    "sending_facility": "ICU",
    "receiving_app": "EMR",
    "receiving_facility": "Lab",
    "message_timestamp": "20190102",
    "message_type": "ORU^R01",
    "message_id": "M001",
    "hl7_version": "2.5.1",
    "patient_location": "",
    "equipment_id": "DEV-001",
}

CONN_ENTRY = {
    "ts": 1234567890.0,
    "uid": "CabcXY",
    "id.orig_h": "10.0.0.155",
    "id.resp_p": 2575,
    "orig_l2_addr": "00:11:22:33:44:55",
    "resp_l2_addr": "aa:bb:cc:dd:ee:ff",
}


def test_payloads_from_logdir_correlates_l2(tmp_path: Path) -> None:
    """Sidecar joins conn.log L2 onto hl7.log entries via uid."""
    logdir = _write_logs(tmp_path, [HL7_ENTRY], [CONN_ENTRY])

    payloads = payloads_from_logdir(logdir)

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["mac_address"] == "00:11:22:33:44:55"
    assert payload["ip_address"] == "10.0.0.155"
    assert payload["name"] == "Infuse-O-Matic"
    assert payload["serial_number"] == "DEV-001"
    assert payload["open_ports_tcp"] == [2575]
    assert payload["external_keys"]["hl7_sending_facility"] == "ICU"
    assert payload["external_keys"]["hl7_receiving_app"] == "EMR"
    assert payload["external_keys"]["hl7_message_types"] == ["ORU^R01"]
    assert payload["external_keys"]["hl7_version"] == "2.5.1"


def test_payloads_synthetic_mac_when_no_conn_log(tmp_path: Path) -> None:
    """When conn.log is absent, fall back to deterministic synthetic MAC."""
    logdir = _write_logs(tmp_path, [HL7_ENTRY], [])

    payloads = payloads_from_logdir(logdir)

    assert len(payloads) == 1
    assert payloads[0]["mac_address"] == "02:00:0a:00:00:9b"


def test_payloads_synthetic_mac_handles_ipv6_source(tmp_path: Path) -> None:
    """IPv6 source addresses hash to a stable MAC instead of crashing."""
    ipv6_entry = {**HL7_ENTRY, "id.orig_h": "2001:db8::1"}
    logdir = _write_logs(tmp_path, [ipv6_entry], [])

    payloads = payloads_from_logdir(logdir)

    assert len(payloads) == 1
    assert payloads[0]["mac_address"] == "02:00:1e:03:d7:e1"


@pytest.mark.django_db
def test_zeek_ingest_creates_asset(tmp_path: Path) -> None:
    """Management command creates an Asset on first ingest."""
    logdir = _write_logs(tmp_path, [HL7_ENTRY], [CONN_ENTRY])

    call_command("zeek_ingest", logdir=str(logdir))

    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert str(asset.mac_address) == "00:11:22:33:44:55"
    assert str(asset.ip_address) == "10.0.0.155"
    assert asset.name == "Infuse-O-Matic"
    assert asset.serial_number == "DEV-001"
    assert asset.open_ports_tcp == [2575]


@pytest.mark.django_db
def test_zeek_ingest_merges_open_ports_on_update(tmp_path: Path) -> None:
    """Re-ingest with a new port merges into existing asset, not duplicates."""
    logdir = _write_logs(tmp_path, [HL7_ENTRY], [CONN_ENTRY])
    call_command("zeek_ingest", logdir=str(logdir))

    second_hl7 = {**HL7_ENTRY, "id.resp_p": 8080, "uid": "CdefZZ"}
    second_conn = {**CONN_ENTRY, "uid": "CdefZZ", "id.resp_p": 8080}
    _write_logs(tmp_path, [second_hl7], [second_conn])
    call_command("zeek_ingest", logdir=str(logdir))

    assert models.Asset.objects.count() == 1
    asset = models.Asset.objects.get()
    assert asset.open_ports_tcp == [2575, 8080]
