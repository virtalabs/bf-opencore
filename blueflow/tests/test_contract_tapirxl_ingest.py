"""Contract: TapirXL post-VRL golden outputs ingest via PUT /api/assets/upsert/."""

import json
from pathlib import Path

import pytest
from rest_framework import status

from blueflow import models

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_OUTPUTS = _REPO_ROOT / "contracts" / "tapirxl" / "golden_outputs.jsonl"


def _load_golden_outputs() -> list[dict]:
    return [
        json.loads(line)
        for line in _GOLDEN_OUTPUTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize(
    "payload",
    _load_golden_outputs(),
    ids=lambda p: p.get("hostname") or p.get("mac_address", "record"),
)
def test_tapirxl_golden_output_ingests(asset_edit_client, payload: dict) -> None:
    """Each vendored golden output upserts successfully and persists key fields."""
    resp = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.data

    asset = models.Asset.objects.get(mac_address=payload["mac_address"].lower())
    assert str(asset.ip_address) == payload["ip_address"]
    assert asset.manufacturer == payload["manufacturer"]
    if "hostname" in payload:
        assert asset.hostname == payload["hostname"]
    if "category" in payload:
        assert asset.category == payload["category"]
    if "app_sw_version" in payload:
        assert asset.app_sw_version == payload["app_sw_version"]
    if "external_keys" in payload:
        assert asset.external_keys == payload["external_keys"]


def test_tapirxl_golden_output_rejects_missing_identity(asset_edit_client) -> None:
    """Known-bad record without mac_address or manufacturer is rejected."""
    resp = asset_edit_client.put(
        "/api/assets/upsert/",
        json.dumps({"hostname": "orphan-host", "ip_address": "10.0.0.1"}),
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
