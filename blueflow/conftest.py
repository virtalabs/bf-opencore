from unittest.mock import patch

import django.core.management
import pytest

from blueflow.celery import celery_app as cp


@pytest.fixture
def celery_app():
    cp.conf.update(
        {
            "broker_url": "memory://",
            "result_backend": None,
            "task_always_eager": True,
        }
    )
    return cp


@pytest.fixture
def setup_assets(django_db_setup, django_db_blocker):
    """Set up the assets in the database."""
    with django_db_blocker.unblock():
        django.core.management.call_command(
            "create_assets", "--filepath", "data/assets.json"
        )


@pytest.fixture
def mock_post():
    with patch("blueflow.celery.tasks.requests.post") as mock_post:
        return_value = mock_post.return_value
        return_value.status_code = 200
        return_value.json = dict
        return_value.raise_for_status.return_value = None
        yield mock_post
