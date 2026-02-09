"""A model for a connector type."""
import importlib
import copy
import logging
import string
from collections import OrderedDict

from django.db import models
from django_celery_beat.models import PeriodicTask
from django.apps import apps
from bf_opencore.exceptions import ConnectorConfigError

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
        connectors = importlib.import_module('connectors')
        try:
            return getattr(connectors, self.id)
        except AttributeError as err:
            logger.error(
                "Expected id '%s' to name a submodule of connectors: %s",
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
