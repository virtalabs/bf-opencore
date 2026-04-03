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
        django.core.management.call_command("loaddata", "data/assets.json")
