from unittest.mock import patch
from bf_opencore.models.viper import ViperWebhookRequest
from bf_opencore.celery.tasks import viper_webhook
from django.apps import apps
from typing import Any
import pytest
import math

def get_asset_count():
    Asset = apps.get_model('bf_opencore', 'Asset')
    return Asset.objects.count()


@pytest.mark.django_db
def test_viper_webhook_output_no_assets(celery_app):
    '''
    Captures the output from the celery task.
    Ensuring it's the same as the expected output.
    '''
    with patch('bf_opencore.celery.tasks.requests.post') as mock_post:
        viper_webhook.apply(args=[ViperWebhookRequest(
            callback='https://example.com/viper/webhook/',
            since='2026-01-01T00:00:00Z',
            before='2026-01-02T00:00:00Z',
            max_pages=1,
            page_size=10,
        ).to_dict()])
        assert mock_post.call_count == 0

def _assert_previous(previous: Any) -> None:
    assert isinstance(previous, str)
    # ensure constructed kwargs exist
    args = [
        "page",
        "page_size",
        "since",
    ]
    for ar in args:
        assert ar in previous
    not_args = [
        "before"
    ]
    for ar in not_args:
        assert ar not in previous

def _assert_next(_next: Any) -> None:
    assert isinstance(_next, str)

@pytest.mark.django_db
def test_viper_webhook_output_with_all_assets(celery_app, setup_assets):
    '''
    Captures the output from the celery task.
    Ensuring it's the same as the expected output.
    '''
    page_size = 10
    total_assets = get_asset_count()
    total_pages = math.ceil(total_assets / page_size)
    with patch('bf_opencore.celery.tasks.requests.post') as mock_post:
        viper_webhook.apply(args=[ViperWebhookRequest(
            callback='https://example.com/viper/webhook/',
            since='1800-01-01T00:00:00Z', # some arbitrary date in the past to get all assets
            before=None,
            max_pages=100, # high enough to get all assets
            page_size=page_size,
        ).to_dict()])
        assert mock_post.call_count == total_pages
        assert mock_post.call_args[0][0] == 'https://example.com/viper/webhook/'
        for i, call in enumerate(mock_post.call_args_list):
            payload = call.kwargs['json']
            assert payload['page'] == 1 + i
            assert payload['page_size'] == page_size
            assert payload['total'] == total_assets
            assert payload['total_pages'] == total_pages
            # urls should only be none at the first and last pages, respectively
            previous = payload['previous_page']
            if i > 0:
                _assert_previous(previous)
            else:
                assert previous is None
            _next = payload['next_page']
            if i + 1 < total_pages:
                _assert_next(_next)
            else:
                assert _next is None

# TODO
@pytest.mark.django_db
def _viper_webhook_output_with_some_assets(celery_app, setup_assets):
    '''
    Captures the output from the celery task.
    Ensuring it's the same as the expected output.
    '''
    page_size = 10
    # total_assets = get_asset_count()
    # total_pages = math.ceil(total_assets / page_size)
    with patch('bf_opencore.celery.tasks.requests.post') as mock_post:
        viper_webhook.apply(args=[ViperWebhookRequest(
            callback='https://example.com/viper/webhook/',
            since='1800-01-01T00:00:00Z', # some arbitrary date in the past to get all assets
            before=None,
            max_pages=100, # high enough to get all assets
            page_size=page_size,
        ).to_dict()])
        # assert mock_post.call_count == total_pages
        assert mock_post.call_args[0][0] == 'https://example.com/viper/webhook/'
        for i, call in enumerate(mock_post.call_args_list):
            payload = call.kwargs['json']
            assert payload['page'] == 1 + i
            assert payload['page_size'] == page_size
            # assert payload['total'] == total_assets
            # assert payload['total_pages'] == total_pages
            # urls should only be none at the first and last pages, respectively
            if i > 0:
                assert isinstance(payload['previous_page'], str)
            else:
                assert payload['previous_page'] is None
            # if i + 1 < total_pages:
            #     assert isinstance(payload['next_page'], str)
            # else:
            #     assert payload['next_page'] is None

