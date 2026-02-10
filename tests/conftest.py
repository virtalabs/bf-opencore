# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""Pytest configuration for bf-opencore tests."""

import os

import pytest


def pytest_configure(config):
    """Set Django settings module for pytest-django before Django is loaded."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.test")


def pytest_ignore_collect(path, config):
    """Ignore tests under tests/blueflow (reference-only; use bf_opencore tests)."""
    try:
        path_str = str(path)
        if "tests" in path_str and "blueflow" in path_str:
            return True
    except Exception:
        pass
    return False


@pytest.fixture(scope="session")
def django_db_setup():
    """Use in-memory SQLite for tests (no DB file)."""
    pass


@pytest.fixture
def auth_client(db):
    """API client authenticated with a regular user."""
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    api_client = APIClient()
    api_client.force_authenticate(user=user)
    return api_client
