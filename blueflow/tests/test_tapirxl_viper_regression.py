"""Regression: TapirXL telemetry → upsert → Viper role propagation.

Drives the full pipeline with golden data from
  .cursor/context/tapirxl_telemetry.jsonl  (TapirXL InventoryRecord wire format)

through the VRL field-mapping logic (mirrored as ``_vrl_transform`` below),
through ``PUT /api/assets/upsert/``, and verifies that the resulting
``ViperWebhookResponse`` items carry the correct ``role`` value.

Three test layers, cheapest first:
  1. ``_vrl_transform`` unit tests — validate the Python mirror of the VRL.
  2. Single-record persistence test — ``category`` survives the upsert.
  3. Full-pipeline regression — all 8 golden records → upsert → Viper ``role``.

If ``configs/upload-vector.vrl`` (in the TapirXL repo) changes its field
mapping, ``_VENDOR_DISPLAY``, ``_PRODUCT_DISPLAY``, and ``_vrl_transform``
below must be updated to match.
"""

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from blueflow.models.viper import ViperWebhookRequest, ViperWebhookResponseList

# ---------------------------------------------------------------------------
# Golden data
# ---------------------------------------------------------------------------

# Sourced from the TapirXL repo's golden_synthetic_philips_inventory.jsonl;
# update this file when TapirXL's golden set changes.
_GOLDEN_JSONL = Path(__file__).parent / "fixtures" / "tapirxl_telemetry.jsonl"

# ---------------------------------------------------------------------------
# Python mirror of configs/upload-vector.vrl (TapirXL repo)
# Keep in sync with that file.
# ---------------------------------------------------------------------------

_VENDOR_DISPLAY: dict[str, str] = {
    "intel": "Intel",
    "microsoft": "Microsoft",
    "paloaltonetworks": "Palo Alto Networks",
    "philips": "Philips",
    "vmware": "VMware",
}

_PRODUCT_DISPLAY: dict[str, str] = {
    "brilliance_ict": "Brilliance iCT",
    "clinical_collaboration_platform": "Clinical Collaboration Platform",
    "intellivue_mx700": "IntelliVue MX700",
    "pan_os": "PAN-OS",
    "windows_10": "Windows 10",
    "windows_7": "Windows 7",
    "windows_server": "Windows Server",
}


def _vrl_transform(record: dict) -> dict:
    """Produce a BlueFlow upsert payload from a TapirXL InventoryRecord.

    Mirrors the strict outbound shape of ``configs/upload-vector.vrl``:
    only declared fields are included; any unmapped source key is dropped.
    """
    out: dict = {}

    out["mac_address"] = record["mac_address"]
    out["ip_address"] = record["ip_address"]

    if record.get("hostname") is not None:
        out["hostname"] = record["hostname"]

    if record.get("vendor") is not None:
        slug = record["vendor"]
        out["manufacturer"] = _VENDOR_DISPLAY.get(slug, slug)

    if record.get("product") is not None:
        slug = record["product"]
        out["model"] = _PRODUCT_DISPLAY.get(slug, slug)

    if record.get("version") is not None:
        out["app_sw_version"] = record["version"]

    if record.get("device_class") is not None:
        out["category"] = record["device_class"]

    out["open_ports_tcp"] = record["open_ports"]

    if record.get("confidence") is not None:
        out["external_keys"] = {"tapirxl_confidence": record["confidence"]}

    return out


def _load_golden() -> list[dict]:
    return [
        json.loads(line)
        for line in _GOLDEN_JSONL.read_text().splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Layer 1: _vrl_transform unit tests
# ---------------------------------------------------------------------------


def test_vrl_transform_maps_device_class_to_category() -> None:
    """device_class → category per the VRL contract."""
    record = {
        "mac_address": "00:09:FB:BD:75:6D",
        "ip_address": "10.10.10.21",
        "hostname": "MX700-bed12",
        "vendor": "philips",
        "product": "intellivue_mx700",
        "version": None,
        "device_class": "patient_monitor",
        "open_ports": [3702],
        "confidence": "LOW",
    }
    out = _vrl_transform(record)
    assert out["category"] == "patient_monitor"
    assert out["manufacturer"] == "Philips"
    assert out["model"] == "IntelliVue MX700"
    assert out["open_ports_tcp"] == [3702]
    assert "app_sw_version" not in out


def test_vrl_transform_omits_category_when_device_class_null() -> None:
    """Null device_class → category absent from output (existing value preserved on upsert)."""
    record = {
        "mac_address": "00:90:20:AA:BB:01",
        "ip_address": "10.10.10.30",
        "hostname": "BRILL-CT01",
        "vendor": "philips",
        "product": "brilliance_ict",
        "version": None,
        "device_class": None,
        "open_ports": [],
        "confidence": "HIGH",
    }
    out = _vrl_transform(record)
    assert "category" not in out


@pytest.mark.parametrize(
    "record",
    [r for r in _load_golden() if r.get("device_class") is not None],
    ids=lambda r: r["ip_address"],
)
def test_vrl_transform_golden_categorised_records(record: dict) -> None:
    """Every categorised golden record produces category == device_class."""
    out = _vrl_transform(record)
    assert out["category"] == record["device_class"]


# ---------------------------------------------------------------------------
# Layer 2: single-record persistence
# ---------------------------------------------------------------------------


def test_device_class_alias_persisted_through_upsert(asset_edit_client) -> None:
    """Raw TapirXL device_class field maps to category when Vector is bypassed."""
    from blueflow import models

    resp = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(
            {
                "mac_address": "DE:AD:BE:EF:00:01",
                "ip_address": "10.10.10.99",
                "device_class": "patient_monitor",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 201
    asset = models.Asset.objects.get(mac_address="de:ad:be:ef:00:01")
    assert asset.category == "patient_monitor"


def test_device_class_persisted_through_upsert(asset_edit_client) -> None:
    """category from VRL transform survives PUT /api/assets/upsert/ → Asset.category."""
    from blueflow import models

    payload = _vrl_transform(
        {
            "mac_address": "00:09:FB:BD:75:6D",
            "ip_address": "10.10.10.21",
            "hostname": "MX700-bed12",
            "vendor": "philips",
            "product": "intellivue_mx700",
            "version": None,
            "device_class": "patient_monitor",
            "open_ports": [3702],
            "confidence": "LOW",
        }
    )

    resp = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 201
    asset = models.Asset.objects.get(mac_address="00:09:fb:bd:75:6d")
    assert asset.category == "patient_monitor"


def test_version_persisted_through_upsert(asset_edit_client) -> None:
    """app_sw_version from VRL transform survives PUT /api/assets/upsert/ → Asset.app_sw_version."""
    from blueflow import models

    payload = _vrl_transform(
        {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "ip_address": "10.0.0.1",
            "hostname": None,
            "vendor": None,
            "product": None,
            "version": "1.2.3",
            "device_class": None,
            "open_ports": [],
            "confidence": None,
        }
    )
    assert payload.get("app_sw_version") == "1.2.3"

    resp = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 201
    asset = models.Asset.objects.get(mac_address="aa:bb:cc:dd:ee:ff")
    assert asset.app_sw_version == "1.2.3"


# ---------------------------------------------------------------------------
# Layer 3: full pipeline regression
# ---------------------------------------------------------------------------


def test_golden_device_class_propagates_to_viper_role(
    asset_edit_client, celery_app
) -> None:
    """All 8 golden TapirXL records: device_class reaches Viper as role.

    Pipeline under test:
      tapirxl_telemetry.jsonl
        → _vrl_transform   (mirrors upload-vector.vrl)
        → PUT /api/assets/upsert/
        → Asset.category
        → ViperWebhookResponseList
        → ViperAsset.role
    """
    records = _load_golden()

    # Phase 1 — upsert all golden records into BlueFlow
    for record in records:
        payload = _vrl_transform(record)
        resp = asset_edit_client.put(
            "/api/assets/upsert/",
            json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code in (200, 201), (
            f"Upsert failed for {record['ip_address']}: {resp.data}"
        )

    # Phase 2 — run the Viper webhook, capturing every outbound POST
    with patch("blueflow.celery.tasks.requests.post") as mock_post:
        from blueflow.celery.tasks import viper_webhook

        viper_webhook.apply(
            args=[
                ViperWebhookRequest(
                    callback="https://viper.example.com/integration/",
                    since="1800-01-01T00:00:00Z",
                    before=None,
                    max_pages=100,
                    page_size=100,
                ).to_dict(),
                    str(uuid.uuid4()),
            ]
        )

    # Flatten all pages into a single IP → role map
    all_items = [
        item
        for call in mock_post.call_args_list
        for item in call.kwargs["json"]["items"]
    ]
    role_by_ip: dict[str, str | None] = {
        item["ip"]: item.get("role") for item in all_items
    }

    # Phase 3 — assert role == device_class for every golden record
    for record in records:
        ip = record["ip_address"]
        expected = record["device_class"]
        assert ip in role_by_ip, f"{ip} missing from Viper output"
        if expected:
            assert role_by_ip[ip] == expected, (
                f"{ip}: expected role={expected!r}, got role={role_by_ip[ip]!r}"
            )
        else:
            assert role_by_ip[ip] is None, (
                f"{ip}: expected role omitted, got role={role_by_ip[ip]!r}"
            )
