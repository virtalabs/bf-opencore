"""Pytest configuration for blueflow tests."""

import os

import pytest


def pytest_configure(config):
    """Set Django settings module for pytest-django before Django is loaded."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.test")


def pytest_ignore_collect(path, config):
    """Ignore tests under tests/blueflow (reference-only; use blueflow tests)."""
    try:
        path_str = str(path).replace("\\", "/")
        if "tests/blueflow" in path_str:
            return True
    except Exception:
        pass
    return False


@pytest.fixture
def enable_core_switch(db):
    """Enable the 'core' waffle switch so API views are allowed in tests.

    Required for all API endpoint tests (e.g. /assets/).
    """
    from waffle.testutils import override_switch

    with override_switch("core", active=True):
        yield


@pytest.fixture(scope="session")
def django_db_setup(
    request,
    django_test_environment,
    django_db_blocker,
    django_db_use_migrations,
    django_db_keepdb,
    django_db_createdb,
    django_db_modify_db_settings,
):
    """Use default DB setup for PostgreSQL (tests use PostgreSQL only, no SQLite)."""
    from django.test.utils import setup_databases, teardown_databases
    from pytest_django.fixtures import _get_databases_for_setup

    setup_databases_args = {}
    if not django_db_use_migrations:
        from pytest_django.fixtures import _disable_migrations

        _disable_migrations()
    if django_db_keepdb and not django_db_createdb:
        setup_databases_args["keepdb"] = True

    aliases, serialized_aliases = _get_databases_for_setup(request.session.items)
    with django_db_blocker.unblock():
        db_cfg = setup_databases(
            verbosity=request.config.option.verbose,
            interactive=False,
            aliases=aliases,
            serialized_aliases=serialized_aliases,
            **setup_databases_args,
        )
    yield
    if not django_db_keepdb:
        with django_db_blocker.unblock():
            try:
                teardown_databases(db_cfg, verbosity=request.config.option.verbose)
            except Exception:
                pass


@pytest.fixture
def auth_client(db, enable_core_switch):
    """Return API client authenticated with a regular user.

    Uses blueflow.tests.factories.make_user.
    """
    from rest_framework.test import APIClient

    from blueflow.tests.factories import make_user

    user = make_user()
    api_client = APIClient()
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(db, enable_core_switch):
    """Return API client authenticated with a superuser.

    For app-level admin-style tests; uses factories.make_superuser.
    """
    from rest_framework.test import APIClient

    from blueflow.tests.factories import make_superuser

    admin_user = make_superuser()
    api_client = APIClient()
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture(autouse=True)
def _auto_db(db):
    """Enable db for all tests.

    Should replace with module level enablement when:
        https://github.com/virtalabs/blueflow/issues/36
    """


