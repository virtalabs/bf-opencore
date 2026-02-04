"""BlueFlow connector tasks.

This table stores information about waiting, running and complete
Celery/RabbitMQ tasks.
"""

import logging
import inspect
import os.path
from collections import OrderedDict
import math

import celery
from django.db import models
from django.db.models import F
from django.utils import timezone
from blueflow.exceptions import ConnectorTaskError
from .connector import Connector

logger = logging.getLogger(__name__)

# Disable UI output if it gets too big.  Avoids a performance bottleneck.
MAX_OUTPUT_LINES = 100


def caller_info():
    """Provide info about caller's caller.

    E.g.
       some_connector()     # A function in a connector
          L34: ctx.print('zap the dingbat')
       ctx.print()          # Print method (of ConnectorTask)
          L56: ci = caller_info()
       caller_info()        # This function
          L25: <getting info about some_connector()

    Return a string that may be inserted in log message, on the form
        "connector.pyL34::some_connector()"
    """
    caller_frame = inspect.stack()[2]  # 2 levels up from here
    return "{filename}L{lineno}::{function}()".format(
        filename=os.path.basename(caller_frame[1]),
        lineno=caller_frame[2],
        function=caller_frame[3])


class ConnectorTask(models.Model):
    """Holds information about running Celery/RabbitMQ tasks."""

    # celery_task_id is a UUID and as such 36 characters
    # (https://en.wikipedia.org/wiki/Universally_unique_identifier)
    # There's no way to force it to be CHAR 36 as opposed to VARCHAR 36
    # (unless we create a custom model field.)  THis is IMHO overkill.
    celery_task_id = models.CharField(max_length=36, unique=True)
    args = models.JSONField(default=list)
    kwargs = models.JSONField(default=OrderedDict)
    attachment = models.FileField(upload_to='tmp_scan', null=True)
    status = models.CharField(max_length=126, blank=True, null=True)
    progress_total = models.IntegerField(default=1000)  # that's plenty
    progress_count = models.IntegerField(default=0)
    stdout = models.TextField(blank=True, default='')
    stdout_count = models.IntegerField(default=0)
    stderr = models.TextField(blank=True, default='')
    stderr_count = models.IntegerField(default=0)
    retval = models.TextField(blank=True, null=True)
    periodic = models.BooleanField(default=False)
    external_url = models.TextField(
        blank=True, null=True,
        help_text="URL to the 'results' of this particular connection",
    )
    date_submitted = models.DateTimeField(default=timezone.now)
    date_started = models.DateTimeField(null=True)
    date_finished = models.DateTimeField(null=True)

    # A ConnectorTask object is associated with exactly one type of Connector.
    # If the Connector is deleted for some reason, orphan this ConnectorTask.
    connector = models.ForeignKey(Connector, null=True,
                                  on_delete=models.SET_NULL)

    @property
    def celery_task_name(self):
        """Return task associated with connector."""
        return self.connector.celery_task_name

    @property
    def display_name(self):
        """Produce the best display name we are able to."""
        return self.connector.display_name

    @property
    def connector_enabled(self):
        """Return True if Connector is enabled."""
        return self.connector.enabled

    def __str__(self):  # noqa
        return "{}:{}:{}".format(
            self.id, self.celery_task_name, self.celery_task_id)

    def append_output(self, message, dest):
        """
        Append to dest, update count, update caller's logger.

        Truncate output if the write count exceeds MAX_OUTPUT_LINES.
        """
        # Sanity check dest
        assert dest in ['stdout', 'stderr']

        # Duplicate message to loggger.  Celery will provide us with the
        # correct logger that corresponds to this worker's celery task id
        celery_task_logger = celery.utils.log.get_task_logger(__name__)
        if dest == 'stdout':
            celery_task_logger.info("%s %s", caller_info(), message)
        else:
            celery_task_logger.warning("%s %s", caller_info(), message)

        # Disable output after too many lines
        #
        # We want a read-modify-write operation, which suffers from two
        # possible problems.
        # 1. Stale read data.  This object (self) may have been loaded from
        #    the database a long time ago.
        # 2. Race condition.  If two processes are trying to write the same
        #    data at the same time.
        # We can solve both of these problems with a Django F-expression,
        # which is an abstraction for a direct database operation that does
        # not first load data into memory.
        #
        # Django docs:
        # https://docs.djangoproject.com/en/2.0/ref/models/expressions/#f-expressions

        # Get most recent value for stdout_count
        self.refresh_from_db()
        if dest == 'stdout':
            count_prev = self.stdout_count
        else:
            count_prev = self.stderr_count

        # Update stdout_count using an atomic database operation.  The actual
        # databse operation will occur on save().
        if dest == 'stdout':
            self.stdout_count = F('stdout_count') + 1
        else:
            self.stderr_count = F('stderr_count') + 1

        # Decide whether to continue printing
        if count_prev == MAX_OUTPUT_LINES:
            message = ("Truncating output after {} lines."
                       "".format(MAX_OUTPUT_LINES))
            celery_task_logger.warning(
                "ctx.append_output: The print above and subsequent ones have "
                "been suppressed from the UI")
        elif count_prev > MAX_OUTPUT_LINES:
            # Keep track of how many total messages
            # (this way we can report on how many truncated ones.)
            self.save()
            self.refresh_from_db()  # Convert F-expression to value
            return

        # Update the database using an atomic database operation.
        # Stack overflow reference
        # https://stackoverflow.com/questions/8143362/django-using-an-f-expression-for-a-text-field-in-an-update-call
        #
        # We're only going to override the operator we need
        class CF(F):
            """Override Django F-expression's '+' operator."""

            ADD = '||'
        message += "\n"
        if dest == 'stdout':
            self.stdout = CF('stdout') + message
        else:
            self.stderr = CF('stderr') + message
        self.save()
        self.refresh_from_db()  # Convert F-expression to value

    def print(self, message):
        """Update stdout using self.append_output()."""
        self.append_output(message, dest='stdout')

    def error(self, message):
        """Update stderr using self.append()."""
        self.append_output(message, dest='stderr')

    ############################
    # Progress related methods

    @property
    def progress(self):
        """Return progress as decimal [0.0, 1.0]."""
        if self.progress_total == 0:
            # If progress_total is 0 it's due to a bug.  The best we can
            # do is check the status to determine if the progress is '0'
            # or '1'.
            if self.status in ["Finished", "Success"]:
                return 1.0
            else:
                return 0.0
        output = self.progress_count / self.progress_total
        if output < 0.0:
            return 0.0
        if output > 1.0:
            return 1.0
        return output

    def set_progress_total(self, progress_total):
        """Set the total number of steps expected for 100% progress.

        Necessary if the default (1000) is not appropriate.
        """
        # progress_total is an integer.  We round up.
        progress_total = math.ceil(progress_total)
        # progress_total is at least 1
        progress_total = max(progress_total, 1)
        self.progress_total = progress_total
        self.save()

    def inc_progress(self):
        """Increment progress_count."""
        # Update stdout_count using an atomic database operation
        self.progress_count = F('progress_count') + 1
        self.save()
        self.refresh_from_db()

        # Duplicate message to loggger.  Celery will provide us with the
        # correct logger that corresponds to this worker's celery task id
        celery_task_logger = celery.utils.log.get_task_logger(__name__)
        celery_task_logger.debug(
            "%s progress: %d/%d %0.2f%%",
            caller_info(),
            self.progress_count,
            self.progress_total,
            self.progress * 100
        )

    def set_progress(self, progress):
        """Mimic old set_progress behavior by setting count and total."""
        # Make sure we're dealing with a number
        try:
            progress = float(progress)
        except (TypeError, ValueError) as err:
            raise ConnectorTaskError(str(err))

        # Coerce bad inputs
        if progress < 0.0:
            progress = 0.0
        elif progress > 1.0:
            progress = 1.0

        # Duplicate message to loggger.  Celery will provide us with the
        # correct logger that corresponds to this worker's celery task id
        celery_task_logger = celery.utils.log.get_task_logger(__name__)
        celery_task_logger.debug(
            "%s progress: (%0.2f)", caller_info(), progress)

        # Calculate progress_count as a fraction of progress_total
        # Note that the default value for progress_total is 1000, but any
        # value will work.
        if progress == 0.0:
            self.progress_count = 0
        elif progress == 1.0:
            self.progress_count = self.progress_total
        else:
            self.progress_count = int(round(progress * self.progress_total))

        self.save()
