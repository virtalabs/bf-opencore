"""ViewSet for periodic tasks, part of django-celery-beat."""

import logging
import django_filters
from rest_framework import viewsets, serializers
from waffle.mixins import WaffleSwitchMixin

from django_celery_beat.models import PeriodicTask, IntervalSchedule, \
    CrontabSchedule
import bf_opencore.models


logger = logging.getLogger(__name__)


class CrontabScheduleSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    # Since we namespace with `api:` we have to specify the view-name.
    # This is a little strange...
    url = serializers.HyperlinkedIdentityField(
        view_name="api:crontabschedule-detail")

    # Human-readable name
    display_name = serializers.SerializerMethodField('do_display_name')

    def do_display_name(self, crontabschedule):
        """Human-readable name."""
        return str(crontabschedule)

    class Meta:  # noqa
        model = CrontabSchedule
        fields = (
            "id",
            "minute",
            "hour",
            "day_of_week",
            "day_of_month",
            "month_of_year",
            "url",
            "display_name",
        )


class CrontabScheduleViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Periodic (crontab) schedule."""

    waffle_switch = "legacy"

    # Model does have objects...
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer


class IntervalScheduleSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    # Since we namespace with `api:` we have to specify the view-name.
    # This is a little strange...
    url = serializers.HyperlinkedIdentityField(
        view_name="api:intervalschedule-detail")

    # Human-readable name
    display_name = serializers.SerializerMethodField('do_display_name')

    def do_display_name(self, intervalschedule):
        """Human-readable name."""
        return str(intervalschedule)

    class Meta:  # noqa
        model = IntervalSchedule
        fields = (
            "id",
            "every",
            "period",
            "url",
            "display_name",
        )


class IntervalScheduleViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Periodic (interval) schedule."""

    waffle_switch = "legacy"

    # Model does have objects...
    queryset = IntervalSchedule.objects.all()
    serializer_class = IntervalScheduleSerializer


class PeriodicTaskSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes periodic tasks.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    # Since we namespace with `api:` we have to specify the view-name.
    # This is a little strange...
    url = serializers.HyperlinkedIdentityField(
        view_name="api:periodictask-detail")
    page_url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:periodictask")
    display_name = serializers.SerializerMethodField('do_display_name')
    display_schedule = serializers.SerializerMethodField('do_display_schedule')
    connector_id = serializers.SerializerMethodField('do_connector_id')
    connector_enabled = serializers.SerializerMethodField(
        'do_connector_enabled'
    )

    def do_display_name(self, periodictask):
        """Server-controlled human-readable name."""
        return periodictask.name

    def do_display_schedule(self, periodictask):
        """Human-readable interval or crontab schedule."""
        if periodictask.interval:
            return str(periodictask.interval)
        if periodictask.crontab:
            return str(periodictask.crontab)
        return None

    def do_connector_id(self, periodictask):
        """Human-readable name."""
        connector = bf_opencore.models.Connector.objects.get(
            celery_task_name=periodictask.task
        )
        return connector.id

    def do_connector_enabled(self, periodictask):
        """Human-readable name."""
        connector = bf_opencore.models.Connector.objects.get(
            celery_task_name=periodictask.task
        )
        return connector.enabled

    # We need to tell DRF how to turn foreign key relationships into URLs
    # and objects.   I will admit that I don't fully understand what's going on
    # in the next few statements.  However, I know that without this code,
    # I get reverse url lookup failures.
    #
    # Django REST Framework documentation on serializer relations:
    # http://www.django-rest-framework.org/api-guide/relations/
    interval = serializers.HyperlinkedRelatedField(
        required=False,
        queryset=IntervalSchedule.objects.all(),
        view_name="api:intervalschedule-detail",
    )
    crontab = serializers.HyperlinkedRelatedField(
        required=False,
        queryset=CrontabSchedule.objects.all(),
        view_name="api:crontabschedule-detail",
    )

    def validate(self, attrs):
        """Exactly one of (interval, crontab) is required.

        Django REST API documentation on validators:
        http://www.django-rest-framework.org/api-guide/validators/
        """
        if self.context['request'].method == 'PATCH' and \
           "interval" not in attrs and "crontab" not in attrs:
            return attrs
        if not bool("interval" in attrs) ^ bool("crontab" in attrs):
            raise serializers.ValidationError(
                "Exactly one of (interval, crontab) is required")
        return attrs

    class Meta:  # noqa
        model = PeriodicTask
        # NOTE HHolm 2017-08-29: I think most of these args are in fact
        #   read-only.  We should consider tagging them as such, like
        #   in connector_task.py:ConnectorTaskSerializer.
        fields = [
            "id",
            "name",
            "task",
            "args",
            "kwargs",
            "queue",
            "exchange",
            "routing_key",
            "expires",
            "enabled",
            "last_run_at",
            "total_run_count",
            "date_changed",
            "description",
            "crontab_id",
            "crontab",
            "interval_id",
            "interval",
            "url",
            "page_url",
            "display_name",
            "display_schedule",
            "connector_enabled",
            "connector_id",
            ]


class PeriodicTaskFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:  # noqa
        model = PeriodicTask

        fields = {
            'name': ['exact'],
            'task': ['exact'],
            }


class PeriodicTaskViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Periodic task."""

    waffle_switch = "legacy"

    # Include only BlueFlow connectors.  This will exclude the Celery Backend
    # Clean up task.
    queryset = PeriodicTask.objects.filter(task__startswith="connectors")
    serializer_class = PeriodicTaskSerializer

    search_fields = ['name']
    filterset_class = PeriodicTaskFilter
