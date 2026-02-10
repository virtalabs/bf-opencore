
"""
Testing connector task methods that write to the UI.

Celery docs on integration with unit tests
http://docs.celeryproject.org/en/latest/userguide/testing.html
"""

import pytest
import django.core.management
import bf_opencore.connectors.celery
import bf_opencore.bf_opencore.models
from bf_opencore import connectors
import models

@pytest.fixture()
def setup_db(db):
    """Create connector objects."""
    # ConnectorTask objects are linked to Connector objects with a foreign key
    # relationship.  We need those objects to be available.
    django.core.management.call_command('create_connectors')

    # First enable Connector that's disabled by default
    connector = models.Connector.objects.get(id="true")
    connector.enabled = True
    connector.save()


def test_simple(setup_db):
    """
    Run a connector task and verify that it was connected to the DB.

    This will implicitely verify that the Celery signals correctly created
    and associated with a ConnectorTask database object.  That means there will
    be exactly one ConnectorTask object in the database.
    """
    connectors.true.main.apply()
    assert models.ConnectorTask.objects.count() == 1


def test_celery_task_id(setup_db):
    """A Celery task ID is created automatically."""
    connectors.true.main.apply()
    ct = models.ConnectorTask.objects.get()
    assert ct.celery_task_id


def test_success_handler(setup_db):
    """Test the Celery success signal handler."""
    connectors.true.main.apply()
    ct = models.ConnectorTask.objects.get()
    assert ct.status == "Success"


def test_failure_handler(setup_db):
    """Test the Celery failure signal handler with details in stderr."""
    connectors.false.main.apply()
    assert models.ConnectorTask.objects.count() == 1
    ct = models.ConnectorTask.objects.get()
    assert ct.status == "Failed"
    assert "File" in ct.stderr
    assert "AssertionError: This is a custom assertion message" in ct.stderr


@pytest.fixture
def test_connector_object():
    """A Connector that we'll use in tests."""
    return models.Connector.objects.create(
        id='test_celery',
        celery_task_name='connectors.tests.test_celery.my_task',
        enabled=True,
        settings={}
    )


@pytest.mark.django_db
def test_simultaneous_print(celery_app, test_connector_object):
    """Two competing ConnectorTask objects writing to stdout."""

    @celery_app.task(bind=True)
    def my_task(ctx):
        """Dummy task."""
        celery_task_id = ctx.request.id

        # Retrieve a copy of a ConnectorTask from the database.  We now have
        # two competing copies: `ct2` and `ctx.ct`.
        ct2 = models.ConnectorTask.objects.get(
            celery_task_id=celery_task_id)

        # Print using ConnectorTask object bound by Celery signal
        ctx.ct.print("hello")

        # Print using Connector Task object retrieved from database *before*
        # first print statement.
        ct2.print("world")

    # Run task using Celery machinery
    my_task.apply()

    # Verify output of task after it's done
    ct = models.ConnectorTask.objects.get()
    assert ct.status == "Success"
    assert ct.stdout == 'hello\nworld\n'
    assert ct.stdout_count == 2
    assert ct.stderr == ''
