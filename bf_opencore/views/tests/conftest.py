import pytest
from rest_framework.test import APIClient

@pytest.fixture
def auth_client():
    return APIClient()