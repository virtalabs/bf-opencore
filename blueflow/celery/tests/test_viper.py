import datetime
import json
import math
import uuid
from unittest.mock import patch

import pytest

from blueflow.celery.tasks import viper_webhook
from blueflow.models import Asset, ViperWebhookJob
from blueflow.models.viper import ViperWebhookRequest


def test_viper_webhook_output_no_assets(celery_app, mock_post):
    """Capture the output from the celery task.

    Ensure it's the same as the expected output.
    """
    request_id = str(uuid.uuid4())
    viper_webhook.apply(
        args=[
            ViperWebhookRequest(
                callback="https://example.com/viper/webhook/",
                since="2026-01-01T00:00:00Z",
                before="2026-01-02T00:00:00Z",
                max_pages=1,
                page_size=10,
            ).to_dict(),
            request_id,
        ]
    )
    assert mock_post.call_count == 0


def _assert_page_query(page_qstring: str, has: list[str], doesnt: list[str]) -> None:
    assert isinstance(page_qstring, str)
    for arg in has:
        assert arg in page_qstring
    for arg in doesnt:
        assert arg not in page_qstring


def test_viper_webhook_output_with_all_assets(celery_app, setup_assets, mock_post):
    """Capture the output from the celery task.

    Ensure it's the same as the expected output.
    """
    page_size = 10
    total_assets = Asset.objects.count()
    total_pages = math.ceil(total_assets / page_size)
    request_id = str(uuid.uuid4())
    viper_webhook.apply(
        args=[
            ViperWebhookRequest(
                callback="https://example.com/viper/webhook/",
                since="1800-01-01T00:00:00Z",  # past date; gets all assets
                before=None,
                max_pages=100,  # high enough to get all assets
                page_size=page_size,
            ).to_dict(),
            request_id,
        ]
    )
    assert mock_post.call_count == total_pages
    assert mock_post.call_args[0][0] == "https://example.com/viper/webhook/"
    for i, call in enumerate(mock_post.call_args_list):
        payload = call.kwargs["json"]
        assert payload["page"] == 1 + i
        assert payload["pageSize"] == page_size
        assert payload["totalCount"] == total_assets
        assert payload["totalPages"] == total_pages
        # request_id, since, before are internal — not on the wire
        assert "request_id" not in payload
        assert "since" not in payload
        assert "before" not in payload

        # urls should only be none at the first and last pages, respectively
        args = [
            "page",
            "page_size",
            "since",
        ]
        not_args = [
            "before",
        ]

        previous = payload["previous"]
        if i > 0:
            _assert_page_query(previous, args, not_args)
        else:
            assert previous is None

        _next = payload["next"]
        if i + 1 < total_pages:
            _assert_page_query(_next, args, not_args)
        else:
            assert _next is None


def test_viper_asset_wire_shape_uses_camel_case(celery_app, setup_assets, mock_post):
    """IntegrationUpload items use camelCase keys per Viper OpenAPI."""
    viper_webhook.apply(
        args=[
            ViperWebhookRequest(
                callback="https://example.com/viper/webhook/",
                since="1800-01-01T00:00:00Z",
                before=None,
                max_pages=100,
                page_size=100,
            ).to_dict(),
            str(uuid.uuid4()),
        ]
    )
    for call in mock_post.call_args_list:
        body = call.kwargs["json"]
        assert "pageSize" in body
        assert "totalCount" in body
        for item in body["items"]:
            assert "upstreamApi" in item
            assert "vendorId" in item
            assert "upstream_api" not in item


@pytest.fixture
def viper_request() -> ViperWebhookRequest:
    return ViperWebhookRequest(
        callback="https://example.com/viper/webhook/",
        since="2026-01-01T00:00:00Z",
        before="2026-01-02T00:00:00Z",
        max_pages=1,
        page_size=10,
    )


def _viper_job(request: ViperWebhookRequest) -> ViperWebhookJob:
    return ViperWebhookJob.objects.create(
        callback=request.callback,
        since=request.since,
        before=request.before,
        request_body=request.to_dict(),
    )


def test_viper_webhook_status_finished(celery_app, setup_assets, viper_request):
    """Job status advances from pending → finished on success."""
    job = _viper_job(viper_request)
    assert job.status == ViperWebhookJob.Status.PENDING

    viper_webhook.apply(args=[viper_request.to_dict(), job.id])

    job.refresh_from_db()
    assert job.status == ViperWebhookJob.Status.FINISHED


def test_viper_webhook_status_error(celery_app, viper_request):
    """Job status advances from pending → error when the task raises."""
    job = _viper_job(viper_request)
    assert job.status == ViperWebhookJob.Status.PENDING

    with patch(
        "blueflow.celery.tasks.ViperWebhookResponseList.from_request",
        side_effect=RuntimeError("boom"),
    ):
        result = viper_webhook.apply(args=[viper_request.to_dict(), job.id])

    assert result.failed()
    job.refresh_from_db()
    assert job.status == ViperWebhookJob.Status.ERROR


def test_webhook_payload_is_json_serializable(celery_app, setup_assets, mock_post):
    """Regression for #159.

    ``ViperWebhookSerializer`` declares ``since``/``before`` as ``DateTimeField``,
    so DRF feeds ``datetime`` objects into ``ViperWebhookRequest``. Both
    ``to_dict()`` outputs must survive ``json.dumps`` (the request payload that
    Celery serializes, and the response body that ``requests.post(json=...)``
    serializes) — otherwise the task crashes with ``TypeError``.
    """
    since = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    before = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    request = ViperWebhookRequest(
        callback="https://example.com/viper/webhook/",
        since=since,
        before=before,
        max_pages=100,
        page_size=10,
    )

    # Request payload (Celery serializes this on .delay()).
    request_payload = request.to_dict()
    round_tripped = json.loads(json.dumps(request_payload))
    assert round_tripped["since"] == since.isoformat()
    assert round_tripped["before"] == before.isoformat()

    viper_webhook.apply(args=[request_payload, str(uuid.uuid4())])

    assert mock_post.call_count >= 1
    for call in mock_post.call_args_list:
        json.dumps(call.kwargs["json"])  # would raise TypeError on a datetime
