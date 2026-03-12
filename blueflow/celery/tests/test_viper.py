import math
import uuid
from unittest.mock import patch

import pytest
from django.apps import apps

from blueflow.celery.tasks import viper_webhook
from blueflow.models import ViperWebhookJob
from blueflow.models.viper import ViperWebhookRequest


def get_asset_count():
    Asset = apps.get_model("blueflow", "Asset")
    return Asset.objects.count()


def test_viper_webhook_output_no_assets(celery_app):
    """Captures the output from the celery task.
    Ensuring it's the same as the expected output.
    """
    request_id = str(uuid.uuid4())
    with patch("blueflow.celery.tasks.requests.post") as mock_post:
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


def test_viper_webhook_output_with_all_assets(celery_app, setup_assets):
    """Captures the output from the celery task.
    Ensuring it's the same as the expected output.
    """
    page_size = 10
    total_assets = get_asset_count()
    total_pages = math.ceil(total_assets / page_size)
    request_id = str(uuid.uuid4())
    with patch("blueflow.celery.tasks.requests.post") as mock_post:
        viper_webhook.apply(
            args=[
                ViperWebhookRequest(
                    callback="https://example.com/viper/webhook/",
                    since="1800-01-01T00:00:00Z",  # some arbitrary date in the past to get all assets
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
            assert payload["page_size"] == page_size
            assert payload["total"] == total_assets
            assert payload["total_pages"] == total_pages
            assert payload["request_id"] == request_id

            # urls should only be none at the first and last pages, respectively
            args = [
                "page",
                "page_size",
                "since",
            ]
            not_args = [
                "before",
            ]

            previous = payload["previous_page"]
            if i > 0:
                _assert_page_query(previous, args, not_args)
            else:
                assert previous is None

            _next = payload["next_page"]
            if i + 1 < total_pages:
                _assert_page_query(_next, args, not_args)
            else:
                assert _next is None


def test_viper_asset_optional_fields_default_empty(celery_app, setup_assets):
    """cpe and role are not yet populated — assert they default to empty strings."""
    with patch("blueflow.celery.tasks.requests.post") as mock_post:
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
        for item in call.kwargs["json"]["items"]:
            assert "cpe" not in item
            assert "role" not in item


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

    with patch("blueflow.celery.tasks.requests.post"):
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

