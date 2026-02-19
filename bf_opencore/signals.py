
"""Callbacks that are run automatically by the Celery worker.

We use these to automatically update the ConnectorTasks database.

Reference:
http://docs.celeryproject.org/en/latest/userguide/signals.html
"""
import traceback as pytraceback
import celery.signals
import django.utils.timezone
from django.apps import apps

# There isn't going to be an 'objects' member on Django ORM classes.
# Furthermore, this file is full of unused inputs.  We're using the interfance

# Get your logger from Celery.  It will add the celery task id to messages.
logger = celery.utils.log.get_task_logger(__name__)


@celery.signals.task_prerun.connect()
def task_prerun(task_id, task, *args, **kwargs):
    """
    Update ConnectorTask database entry with "Running" status.

    Celery Documentation:
    http://docs.celeryproject.org/en/latest/userguide/signals.html#task-prerun
    Dispatched before a task is executed.
    Sender is the task object being executed.
    """
    logger.debug("task_prerun(task_id=%s)", task_id)

    # When a task is run asynchronously by a worker, the name looks like
    # 'bf_opencore.sleep.__main__.main'.  When it is run synchronously from the
    # command line, it looks like 'app.bf_opencore.sleep.__main__.main'.  Make
    # them both look the same.
    task_name = task.name.replace("app.", "")

    # Do nothing if task is *not* a BlueFlow connector
    if not task_name.startswith("bf_opencore"):
        return

    # Create database entry if it isn't already there.  When a task is run
    # asynchronously from the web UI, it will already have a DB entry.  When
    # a task is run synchronously from the CLI, we need to create it.
    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    Connector = apps.get_model('bf_opencore', 'Connector')
    try:
        connector_task = ConnectorTask.objects.get(
            celery_task_id=task_id)
    except ConnectorTask.DoesNotExist:
        connector = Connector.objects.get(celery_task_name=task_name)
        connector_task = ConnectorTask(
            celery_task_id=task_id,
            connector=connector,
            args=kwargs['args'],
            kwargs=kwargs['kwargs'],
            )
        connector_task.save()  # Need to get ID before print
        print("Created ConnectorTask %s" % connector_task)

    # Bind a reference to the connector_task object to the celery task context.
    task.ct = connector_task

    # Update the timeststamp that the task started
    connector_task.date_started = django.utils.timezone.now()

    # Fail disabled connectors
    if not connector_task.connector.enabled:
        connector_task.stderr += (
            "Connector is disabled.  See the settings page.\n"
        )
        connector_task.status = "Failed"
        connector_task.save()
        return

    # Set the status
    connector_task.status = "Running"
    connector_task.save()


@celery.signals.task_postrun.connect()
def task_postrun(task_id, task, retval, state, *args, **kwargs):
    """
    Update the ConnectorTask DB with output, return value and timestamp.

    Celery Documentation:
    http://docs.celeryproject.org/en/latest/userguide/signals.html#task-postrun
    Dispatched after a task has been executed.  Sender is the task object
    executed.  Note that this hook runs even when there has been an exception
    thrown by the task
    """
    logger.debug("task_postrun(task_id=%s)", task_id)
    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    try:
        connector_task = ConnectorTask.objects.get(
            celery_task_id=task_id)
    except ConnectorTask.DoesNotExist:
        # This case will be triggered by non-BlueFlow tasks
        return

    # Remove ConnectorTask object binding
    if hasattr(task, "ct"):
        delattr(task, "ct")

    # Update the database
    # NOTE: we're not using the `task.ct` attribute because it may have been
    # updated in the mean time by a different Celery signal.  Safer to use the
    # object retrieved from the database.
    if connector_task.status == "Running":
        connector_task.status = "Finished"
    if retval is not None:
        connector_task.retval = retval
    connector_task.date_finished = django.utils.timezone.now()
    connector_task.progress_count = connector_task.progress_total
    connector_task.save()


@celery.signals.task_retry.connect()
def task_retry(request, reason, einfo, *args, **kwargs):
    """
    Update the ConnectorTask DB entry with "Retry" status.

    Celery Documentation:
    http://docs.celeryproject.org/en/latest/userguide/signals.html#task-retry
    """
    logger.debug("task_retry(request=%s)", request)
    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    try:
        task_id = request.id
        connector_task = ConnectorTask.objects.get(
            celery_task_id=task_id)
    except ConnectorTask.DoesNotExist:
        # This case will be triggered by non-BlueFlow tasks
        return
    connector_task.status = "Retry"
    connector_task.save()


@celery.signals.task_success.connect()
def task_success(result, *args, **kwargs):
    """
    Update the ConnectorTask DB entry with "Success" status.

    Celery Documentation:
    http://docs.celeryproject.org/en/latest/userguide/signals.html#task-success
    """
    logger.debug("task_success(result=%s)", result)
    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    try:
        task_id = kwargs['sender'].request.id
        connector_task = ConnectorTask.objects.get(
            celery_task_id=task_id)
    except ConnectorTask.DoesNotExist:
        # This case will be triggered by non-BlueFlow tasks
        return
    if connector_task.status in ("Finished", "Running"):
        connector_task.status = "Success"
    connector_task.save()


@celery.signals.task_failure.connect()
def task_failure(task_id, exception, traceback, einfo, *args, **kwargs):
    """
    Update the ConnectorTask DB entry with "Failed" status.

    Celery Documentation:
    http://docs.celeryproject.org/en/latest/userguide/signals.html#task-failure
    """
    logger.debug("task_failure(task_id=%s)", task_id)
    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    try:
        connector_task = ConnectorTask.objects.get(
            celery_task_id=task_id)
    except ConnectorTask.DoesNotExist:
        # This case will be triggered by non-BlueFlow tasks
        return

    # Append traceback to stderr field and mark status as "Failed"
    for line in pytraceback.format_tb(traceback):
        connector_task.stderr += line.rstrip() + "\n"
    connector_task.stderr += "%s: %s\n" % (
        type(exception).__name__, str(exception).rstrip())
    connector_task.status = "Failed"
    connector_task.save()


@celery.signals.task_revoked.connect()
def task_revoked(request, terminated, signum, expired, *args, **kwargs):
    """
    Update the ConnectorTask DB entry with "Canceled" status.

    Celery Documentation:
    http://docs.celeryproject.org/en/latest/userguide/signals.html#task-revoked
    """
    logger.debug("task_revoke(request=%s)", request)
    ConnectorTask = apps.get_model('bf_opencore', 'ConnectorTask')
    try:
        task_id = request.id
        connector_task = ConnectorTask.objects.get(
            celery_task_id=task_id)
    except ConnectorTask.DoesNotExist:
        # This case will be triggered by non-BlueFlow tasks
        return
    connector_task.status = "Canceled"
    connector_task.save()
