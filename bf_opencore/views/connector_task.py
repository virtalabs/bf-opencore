"""ViewSet for connector tasks."""

import json
import logging
import traceback
from collections import OrderedDict

import celery
import kombu.exceptions  # Celery exceptions

import django_filters
from rest_framework import viewsets, serializers
from rest_framework.parsers import MultiPartParser, JSONParser
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import Connector, ConnectorTask


logger = logging.getLogger(__name__)


class ConnectorTaskSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes connector tasks.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="bf_opencore:connectortask-detail")
    connector = serializers.HyperlinkedRelatedField(
        required=True,
        queryset=Connector.objects.all(),
        view_name="bf_opencore:connector-detail",
    )

    class Meta:  # noqa
        model = ConnectorTask
        read_only_fields = (
            'celery_task_id',
            'args',
            'stdout',
            'stderr',
            'retval',
            'periodic',
            'external_url',
            'date_submitted',
            'date_started',
            'date_finished',
            )
        # Only connector_id and kwargs are "writable".  We don't allow
        # "non-keyword args" to be submitted.  Also, 'status' is writable
        # to support canceling a task via a PATCH/update.
        _writable_fields = (
            'connector_id',
            'kwargs',
            'status',
        )
        _auto_fields = (
            'id',
            'url',
            'display_name',
            'connector',
            'connector_id',
            'celery_task_name',
            'progress',
            'connector_enabled',
        )
        fields = _writable_fields + read_only_fields + _auto_fields
        # We could maybe have used `fields = '__all__'` here; difference
        # is that `id` would not have been included by default.

    def validate(self, attrs):
        """Check that the arguments are relevant and on correct format."""
        if 'connector' in attrs and 'kwargs' in attrs:
            # Request to create a new connector task
            connector = attrs['connector']
            kwargs = attrs.get('kwargs', {})
            errors = OrderedDict()
            for key, kwarg_spec in connector.kwargs_internal_value.items():
                if key in kwargs:
                    kwarg_type = kwarg_spec['type']
                    value = kwargs[key]
                    if value is None:
                        # Don't attempt any conversion, i.e., keep
                        # kwargs[key] as it was
                        continue
                    if value == '':
                        # Convert an empty string to None/null
                        kwargs[key] = None
                        continue
                    try:
                        kwargs[key] = kwarg_type(value)
                    except ValueError:
                        errmsg = "'{}': bad type, must be '{}'".format(
                            value, kwarg_type.__name__)
                        errors[key] = [errmsg]
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def validate_status(self, value):
        """Verify 'status' is "Canceled"."""
        if value.lower() != 'canceled':
            raise serializers.ValidationError("Only 'Canceled' is supported.")
        return value

    def create(self, validated_data):
        """
        Create `ConnectorTask` instance and start task via celery.

        Reference celery issue RE creating Celery Tasks with a known ID.
        https://docs.djangoproject.com/en/1.11/ref/models/instances/
        """
        # Create a UUID for the celery task ahead of time.  We want to avoid
        # a race condition where the task tries lookup its ConnectorTask DB
        # entry doesn't find it, and tries to create it.
        celery_task_id = celery.uuid()
        validated_data.update(
            celery_task_id=celery_task_id,
            status="Submitted",
            periodic=False,
        )
        connector_task = ConnectorTask.objects.create(**validated_data)

        # Verify that the connector is enabled
        if not connector_task.connector.enabled:
            connector_task.stderr += (
                "Connector is disabled.  See the settings page.\n"
            )
            connector_task.status = "Failed"
            connector_task.save()
            return connector_task

        # Now we can start the task with the known task_id.  Pass it the kwargs
        # that accompanied the POST request.  Note that the database will
        # provide defaults values (kwargs={}) if the user does not provide any.
        try:
            connector_task.connector.function.apply_async(
                kwargs=connector_task.kwargs,
                task_id=celery_task_id,
            )
            logger.debug("Queued job %s kwargs=%s",
                         connector_task.connector.function,
                         connector_task.kwargs)
        except (TypeError, kombu.exceptions.OperationalError) as err:
            logger.warning("Error queueing job %s kwargs=%s: %s",
                           connector_task.connector.function,
                           connector_task.kwargs, str(err))
            connector_task.status = "Failed"
            connector_task.returned = str(err)
            for line in traceback.format_stack():
                connector_task.stderr += line.rstrip() + "\n"
            connector_task.save()

        # The create method must return an object instance
        return connector_task

    def update(self, instance, validated_data):
        """Update/PATCH a ConnectorTask instance.

        We're only supporting updating the 'status' field - this is done
        in order to cancel the task.  Effectively, we don't actually
        change it, but we wait for the signals.py::task_revoked signal
        to do that.

        Django REST Framework documentation:
        http://www.django-rest-framework.org/api-guide/serializers/#saving-instances

        Celery documentation:
        http://docs.celeryproject.org/en/latest/reference/celery.app.control.html#celery.app.control.Control.revoke

        """
        # 'instance' is the ConnectorTask instance.
        if 'status' in validated_data:
            assert validated_data['status'].lower() == 'canceled', (
                "'Canceled' status should have been validated in "
                "validate_status()")
            if instance.status == "Submitted" or instance.status == "Running":
                # Should we also update the status to something like
                # "canceling"?  What if the Celery process fails to pick
                # up the signal, and the task_revoked callback isn't
                # called?  Having a "Canceling" state would give
                # important forensic clues.
                celery.task.control.revoke(instance.celery_task_id,
                                           terminate=True)
        return instance


class ConnectorTaskFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:  # noqa
        model = ConnectorTask

        fields = {
            'connector_id': ['exact'],
            }


class ConnectorTaskViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """A ConnectorTask represents a "run" of a Connector."""

    waffle_switch = "core"

    queryset = ConnectorTask.objects.all()
    serializer_class = ConnectorTaskSerializer

    parser_classes = (MultiPartParser, JSONParser)

    search_fields = ['celery_task_name', 'status']
    filterset_class = ConnectorTaskFilter

    def perform_create(self, serializer):
        """Intercept form submission to massage fields, handle uploads."""
        logger.debug('perform_create(): self.request.data=%s',
                     self.request.data)
        attachment = self.request.data.get('attachment', None)

        # check whether attachment is None to see if we're using the
        # MultiPartParser or the JSONParser. there doesn't seem to be a
        # direct way to fetch the relevant parser...
        if attachment is not None:
            # multipart
            kwargs = json.loads(self.request.data.get('kwargs'))
        else:
            # json
            kwargs = self.request.data.get('kwargs')
        serializer.save(kwargs=kwargs, attachment=attachment)
