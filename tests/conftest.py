# Copyright (C) 2026 Virta Laboratories, Inc.  All rights reserved.

"""Pytest configuration for bf-opencore tests."""

import os

import pytest


def pytest_configure(config):
    """Set Django settings module for pytest-django before Django is loaded."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")


@pytest.fixture(scope="session")
def django_db_setup():
    """Use in-memory SQLite for tests (no DB file)."""
    pass
