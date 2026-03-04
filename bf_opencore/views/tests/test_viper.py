import datetime
from unittest.mock import patch

from bf_opencore.models.viper import ViperWebhookRequest

CALLBACK = "https://example.com/viper/webhook/"


def test_viper_webhook(auth_client, celery_app):
    """Asserts our 202 response and call to the celery task."""
    with patch("bf_opencore.celery.tasks.viper_webhook.delay") as mock_viper_webhook:
        response = auth_client.post(
            "/api/viper/webhook/",
            {
                "callback": CALLBACK,
                "since": "2026-01-01T00:00:00Z",
                "before": "2026-01-02T00:00:00Z",
                "max_pages": 1,
                "page_size": 10,
            },
            content_type="application/json",
        )
        assert response.status_code == 202, response.data
        assert response.data == None
        assert mock_viper_webhook.call_count == 1
        mock_viper_webhook.assert_called_once_with(
            ViperWebhookRequest(
                callback=CALLBACK,
                since=datetime.datetime.fromisoformat("2026-01-01T00:00:00Z"),
                before=datetime.datetime.fromisoformat("2026-01-02T00:00:00Z"),
                max_pages=1,
                page_size=10,
            ).to_dict()
        )
