import datetime
import uuid
from unittest.mock import patch

from rest_framework import status

CALLBACK = "https://example.com/viper/webhook/"
MAX_PAGES = 1
PAGE_SIZE = 10


def test_viper_webhook(auth_client, celery_app):
    """Asserts our 202 response and call to the celery task."""
    with patch("blueflow.celery.tasks.viper_webhook.delay") as mock_viper_webhook:
        response = auth_client.post(
            "/api/viper/webhook/",
            {
                "callback": CALLBACK,
                "since": "2026-01-01T00:00:00Z",
                "before": "2026-01-02T00:00:00Z",
                "max_pages": MAX_PAGES,
                "page_size": PAGE_SIZE,
            },
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED, response.data
        assert "request_id" in response.data
        assert uuid.UUID(response.data["request_id"])  # valid UUID
        assert mock_viper_webhook.call_count == 1
        (call_payload, call_request_id), _ = mock_viper_webhook.call_args
        assert call_request_id == response.data["request_id"]
        assert call_payload["callback"] == CALLBACK
        assert call_payload["max_pages"] == MAX_PAGES
        assert call_payload["page_size"] == PAGE_SIZE
        # Compare timestamps by instant — DRF returns the datetime in the
        # project's TIME_ZONE, so the ISO string may not be the UTC form
        # used in the request body, but it must round-trip to the same moment.
        assert datetime.datetime.fromisoformat(
            call_payload["since"]
        ) == datetime.datetime.fromisoformat("2026-01-01T00:00:00+00:00")
        assert datetime.datetime.fromisoformat(
            call_payload["before"]
        ) == datetime.datetime.fromisoformat("2026-01-02T00:00:00+00:00")


def test_viper_webhook_bad_request(auth_client):
    """Ensure a bad request triggers the serializer."""
    response = auth_client.post(
        "/api/viper/webhook/", {}, content_type="application/json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST, response.data
    error = response.data
    required = ["callback", "since", "max_pages", "page_size"]
    assert required == list(error.keys()), (
        f"{required}, are all required, but found {error.keys()}"
    )
