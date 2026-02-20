from unittest.mock import patch
from bf_opencore.models.viper import ViperWebhookRequest, ViperWebhookResponse, ViperAsset
from bf_opencore.celery.tasks import viper_webhook
import pytest

@pytest.mark.django_db
def test_viper_webhook_output(celery_app):
    '''
    Captures the output from the celery task.
    Ensuring it's the same as the expected output.
    '''
    with patch('bf_opencore.celery.tasks.requests.post') as mock_post:
        viper_webhook.delay(ViperWebhookRequest(
            callback='https://example.com/viper/webhook/',
            since='2026-01-01T00:00:00Z',
            before='2026-01-02T00:00:00Z',
            page=1,
            page_size=10,
        ).to_dict())
        assert mock_post.call_count == 1
        assert mock_post.call_args[0][0] == 'https://example.com/viper/webhook/'
        assert mock_post.call_args[0][1] == ViperWebhookResponse(
            items=[],
            page=1,
            page_size=10,
            total=0,
            total_pages=0,
            next_page=None,
            previous_page=None,
        ).to_dict()
