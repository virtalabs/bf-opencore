import pytest
from rest_framework.test import APIClient
from bf_opencore.celery import celery_app as cp

@pytest.fixture
def auth_client():
    return APIClient()

@pytest.fixture
def celery_app():
    cp.conf.update({
        'broker_url': 'memory://',
        'result_backend': None,
        'task_always_eager': True,
    })
    return cp