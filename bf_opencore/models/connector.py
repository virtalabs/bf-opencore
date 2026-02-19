"""A model for a connector type."""
import importlib
import copy
import logging
import string
from collections import OrderedDict
import inspect
import os.path
import math

import celery
from django.db import models
from django_celery_beat.models import PeriodicTask
from django.apps import apps
from django.db import models
from django.db.models import F
from django.utils import timezone

from bf_opencore.exceptions import ConnectorConfigError, ConnectorTaskError

logger = logging.getLogger(__name__)


def get_connector_risk_factor_parameters(connector_module):
    """Extract risk parameters out of the connector spec.

    Returns a dictionary of risk factor parameters, or an empty dictionary if
    this connector does not have an associated RiskFactor.

    This needs to be an independent function (rather than a member function)
    because a migration uses it.
    """
    if not hasattr(connector_module, 'DEFAULT_RISK_SCORE_PARAMS'):
        return {}
    rparams = connector_module.DEFAULT_RISK_SCORE_PARAMS
    if not len(rparams) == 1:
        raise ConnectorConfigError(
            "Malformed DEFAULT_RISK_SCORE_PARAMS "
            "(should be 1-element list): {}".format(rparams))
    rparams = rparams[0]  # 1-element list for (obsolete) historical reasons
    try:
        rf_param = dict(
            shortname=rparams['shortname'],
            name=rparams['name'],
            factor_type=rparams['factor_type'],
            range_min=rparams['min'],
            range_max=rparams['max'],
            # For connectors, the most likely setting for 'scalar' is
            # 'true', i.e., the connector will obtain a scalar value
            # (not True/False)
            scalar=rparams.get('scalar', True),
            default_value=rparams.get('default_value', rparams['min']),
            user_editable=rparams.get('user_editable', False),
            description=rparams.get('description'),
            # All connectors have default weight 0 - it may not
            # be used and it's easy to change.
            weight=0.0,
        )
    except KeyError as err:
        raise ConnectorConfigError(
            "Malformed DEFAULT_RISK_SCORE_PARAMS in connector {}: {}"
            "".format(connector_module, err))
    return rf_param


class Connector(models.Model):
    """Represent one type of connector."""

    id = models.CharField(
        max_length=126,
        primary_key=True,
        help_text="A submodule of the connectors module.",
    )
    celery_task_name = models.TextField(
        help_text="Full function as str. E.g., connectors.sleep.__main__.main",
    )
    settings = models.JSONField(default=OrderedDict)

    enabled = models.BooleanField(default=False)

    @property
    def module(self):
        """Return the enclosing module object.

        This helper function will be used later to extract the Connector
        CONNECTOR_SPEC, DEFAULT_RISK_SCORE_PARAMS, etc.
        """
        bf_opencore = importlib.import_module('bf_opencore')
        try:
            return getattr(bf_opencore, self.id)
        except AttributeError as err:
            logger.error(
                "Expected id '%s' to name a submodule of bf_opencore: %s",
                self.id, err,
            )
            raise err

    @property
    def connector_spec(self):
        """Return the original connector spec object.

        Fetch the CONNECTOR_SPEC object from the connectors module and return
        it.  Include any non-serializable code, like "type".
        """
        return self.module.CONNECTOR_SPEC

    @property
    def display_name(self):
        """Return display_name from CONNECTOR_SPEC object."""
        return self.connector_spec['display_name']

    @property
    def description(self):
        """Return description from CONNECTOR_SPEC object."""
        return self.connector_spec['description']

    @property
    def hidden(self):
        """Return hidden from CONNECTOR_SPEC object."""
        try:
            return self.connector_spec.get('hidden', False)
        except AttributeError as err:
            # Can't actually find the connector in the file system, even
            # though it exists in the database.  We say to the frontend
            # that it is "hidden" and hopefully it'll stop asking.
            # (This way we fail gracefully.)
            logger.error("Can't get hidden prop of '%s', default to True: %s",
                         self.id, err)
            return True  # Hidden

    @property
    def kwargs_internal_value(self):
        """Return kwargs from CONNECTOR_SPEC object.

        In these, the type field is in fact the actual type.
        """
        return self.connector_spec['kwargs']

    @property
    def kwargs(self):
        """Return kwargs from CONNECTOR_SPEC object.

        In these, the type field is a string representing the actual type.
        """
        kwargs = copy.deepcopy(self.kwargs_internal_value)
        for _, kwarg_spec in kwargs.items():
            typename = kwarg_spec['type'].__name__
            kwarg_spec['type'] = typename
        return kwargs

    @property
    def settings_spec_internal_value(self):
        """Return settings from CONNECTOR_SPEC object.

        In these, the type field is in fact the actual type.
        """
        return self.connector_spec.get('settings', dict())

    @property
    def settings_spec(self):
        """Return settings from CONNECTOR_SPEC object.

        In these, the type field is a string representing the actual type.
        """
        settings_spec = copy.deepcopy(self.settings_spec_internal_value)
        for _, spec in settings_spec.items():
            typename = spec['type'].__name__
            spec['type'] = typename
        return settings_spec

    def url_for_asset(self, key):
        """Use a template stored in connector settings to make an asset URL.

        Not every connector needs to be able to generate asset URLs, since not
        every connector deals with individual assets.  To be able to generate
        an asset URL, the connector must define the following settings:
         - external_url_template, a template string (in the manner of Python
           string.Template) that has the following slots:
            * key: will be filled in by this function

        Returns a URL (a string), or None if this connector doesn't have the
        configuration described above.
        """
        try:
            tmpl = self.settings['external_url_template']
            val = string.Template(tmpl).substitute({'key': key})
            return val
        except KeyError:
            return None

    @property
    def function(self):
        """Return function object corresponding to celery_task_name."""
        return self.module.main

    def update_or_create_settings(self):
        """Update or create settings unless already set."""
        updated = False
        for setting, spec in self.settings_spec.items():
            if setting not in self.settings:
                updated = True
                if spec['default'] is None:
                    # We convert None to empty string.  Otherwise, the REST API
                    # and front end try to set the value to the string "None"
                    self.settings[setting] = ''
                else:
                    self.settings[setting] = spec['default']
        if updated:
            self.save()
        return updated

    @property
    def risk_factor_params(self):
        """Risk factor parameters."""
        return get_connector_risk_factor_parameters(self.module)

    def update_or_create_risk_factors(self):
        """Update or create RiskFactor objects read from connector source code.

        The present implementation reads original parameters from a
        connector's module, specifically the DEFAULT_RISK_SCORE_PARAMS
        structure.
        """
        # Get RiskFactor parameters from dictionary in connector module
        rf_param = self.risk_factor_params

        # Do nothing if no risk factor
        if not rf_param:
            logger.debug("No RiskFactor params in connector '%s'", self.id)
            return

        # Create RiskFactor object
        RiskFactor = apps.get_model('bf_opencore', 'RiskFactor')
        rf_param["connector"] = self
        rf, created = RiskFactor.objects.get_or_create(
            shortname=rf_param['shortname'],
            defaults=rf_param,
        )
        # Update value only for newly added RiskFactor properties.  The only
        # way to know if a property is new and needs a default value is if the
        # value from the database is null.
        changed = False
        for key, default_value in rf_param.items():
            if getattr(rf, key) is None:
                setattr(rf, key, default_value)
                changed = True
        if changed:
            rf.save()

        RiskFactor.objects.normalize_weights()

        logger.info(
            "%s RiskFactor '%s' (id %s) for connector '%s'",
            "Created" if created else "Updated", rf, rf.id, self.id
        )

    def save(self, *args, **kwargs):
        """Handle transition from enabled to disabled and vice versa."""
        # Load previous value of "enabled" from the database
        try:
            connector_prev = Connector.objects.get(id=self.id)
            enabled_prev = connector_prev.enabled
        except Connector.DoesNotExist:
            # If the connector does not exist, then this is *not* a transition
            # from enabled to disabled or vice versa.  Indicate non-transition
            # with current value == previous value.
            enabled_prev = self.enabled

        # First call Django's save().  We do this first for exception safety.
        super().save(*args, **kwargs)

        # Transition from disabled to enabled: do nothing
        if not enabled_prev and self.enabled:
            logger.debug("Enabling %s connector", self.id)

        # Transition from enabled to disabled: disable any PeriodicTasks
        elif enabled_prev and not self.enabled:
            disabled_pt = (PeriodicTask.objects
                           .filter(task=self.celery_task_name)
                           .update(enabled=False))
            logger.debug("Disabling %s connector: disabled %s PeriodicTasks",
                         self.id, disabled_pt)

    def __str__(self):  # noqa
        return "{}:{}".format(self.id, self.celery_task_name)

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
    """BlueFlow connector tasks.

    This table stores information about waiting, running and complete
    Celery/RabbitMQ tasks.
    """
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

    def append_output(self, message, dest, max_output_lines=MAX_OUTPUT_LINES):
        """
        Append to dest, update count, update caller's logger.
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
        if count_prev == max_output_lines:
            message = ("Truncating output after {} lines."
                       "".format(max_output_lines))
            celery_task_logger.warning(
                "ctx.append_output: The print above and subsequent ones have "
                "been suppressed from the UI")
        elif count_prev > max_output_lines:
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