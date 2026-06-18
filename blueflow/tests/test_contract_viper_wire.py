"""Contract: BlueFlow → Viper wire tests via Prism mock (no requests.post patch)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests

from blueflow.celery.tasks import _send_viper_payload, viper_webhook
from blueflow.contracts.prism_viper import (
    DEFAULT_INTEGRATION_TOKEN,
    INTEGRATION_UPLOAD_PATH,
    build_prism_callback_url,
)
from blueflow.models import Asset, ViperWebhookJob
from blueflow.models.viper import ViperWebhookRequest

pytestmark = pytest.mark.contract

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VIPER_FIXTURES = _REPO_ROOT / "contracts" / "fixtures" / "viper"

_GEHEALTHCARE_ASSETS: list[dict] = [
    {
        "hostname": "BRIGHTSPEED01",
        "ip_address": "10.40.2.20",
        "mac_address": "00:10:18:AA:BB:01",
        "manufacturer": "gehealthcare",
        "model": "brightspeed_elite_select",
        "app_sw_version": "11.2.0",
        "category": "CT",
    },
    {
        "hostname": "PACS-CENTRICITY-001",
        "ip_address": "10.40.2.10",
        "mac_address": "00:1A:2B:3C:51:10",
        "manufacturer": "gehealthcare",
        "model": "centricity_pacs_iw",
        "category": "pacs",
    },
]


def _viper_auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("VIPER_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_success_viper_send_result(result: str) -> bool:
    """True when _send_viper_payload completed pages (list), not an HTTP error body."""
    parsed = json.loads(result)
    return isinstance(parsed, list)


@pytest.fixture
def viper_prism_callback_url() -> str:
    base = os.environ.get("VIPER_PRISM_BASE_URL")
    if not base:
        pytest.skip(
            "VIPER_PRISM_BASE_URL not set — start Prism (see contracts/viper/README.md)"
        )
    return build_prism_callback_url(base)


@pytest.fixture
def seed_ge_assets(django_db_blocker) -> None:
    from django.utils import timezone

    with django_db_blocker.unblock():
        for fields in _GEHEALTHCARE_ASSETS:
            mac = fields["mac_address"]
            defaults = {k: v for k, v in fields.items() if k != "mac_address"}
            Asset.objects.update_or_create(mac_address=mac, defaults=defaults)
            asset = Asset.objects.get(mac_address=mac)
            asset.update_usage(timezone.now())


def test_prism_callback_url_matches_integration_upload_path() -> None:
    url = build_prism_callback_url("http://127.0.0.1:4010")
    expected_path = INTEGRATION_UPLOAD_PATH.replace("{token}", DEFAULT_INTEGRATION_TOKEN)
    assert url == f"http://127.0.0.1:4010{expected_path}"
    assert "{token}" not in url


def test_send_viper_payload_post_accepted_by_prism(
    seed_ge_assets, viper_prism_callback_url: str
) -> None:
    request = ViperWebhookRequest(
        callback=viper_prism_callback_url,
        since="1800-01-01T00:00:00Z",
        before=None,
        max_pages=100,
        page_size=100,
    )
    result = _send_viper_payload(request, request_id="")
    assert _is_success_viper_send_result(result)


def test_viper_webhook_delivers_conformant_payload(
    celery_app, seed_ge_assets, viper_prism_callback_url: str, django_db_blocker
) -> None:
    with django_db_blocker.unblock():
        job = ViperWebhookJob.objects.create(
            callback=viper_prism_callback_url,
            since="1800-01-01T00:00:00Z",
            before=None,
            request_body={},
        )
        job_id = str(job.id)

    result = viper_webhook.apply(
        args=[
            ViperWebhookRequest(
                callback=viper_prism_callback_url,
                since="1800-01-01T00:00:00Z",
                before=None,
                max_pages=100,
                page_size=100,
            ).to_dict(),
            job_id,
        ]
    )
    assert _is_success_viper_send_result(result.get())


def test_prism_rejects_missing_required_field(
    viper_prism_callback_url: str,
) -> None:
    payload = json.loads(
        (_VIPER_FIXTURES / "sample_page_missing_field.json").read_text(encoding="utf-8")
    )
    payload["next"] = None
    payload["previous"] = None
    response = requests.post(
        viper_prism_callback_url,
        json=payload,
        headers=_viper_auth_headers(),
        timeout=10,
    )
    assert response.status_code >= 400
