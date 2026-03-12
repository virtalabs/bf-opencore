"""ViewSet for periodic tasks, part of django-celery-beat."""

import logging

import django_filters
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask
from rest_framework import serializers, viewsets
from waffle.mixins import WaffleSwitchMixin

logger = logging.getLogger(__name__)


class CrontabScheduleSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:crontabschedule-detail"
    )

    # Human-readable name
    display_name = serializers.SerializerMethodField("do_display_name")

    def do_display_name(self, crontabschedule):
        """Human-readable name."""
        return str(crontabschedule)

    class Meta:
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

    waffle_switch = "core"

    # Model does have objects...
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer


class IntervalScheduleSerializer(serializers.HyperlinkedModelSerializer):
    """Serializer.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:intervalschedule-detail"
    )

    # Human-readable name
    display_name = serializers.SerializerMethodField("do_display_name")

    def do_display_name(self, intervalschedule):
        """Human-readable name."""
        return str(intervalschedule)

    class Meta:
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

    waffle_switch = "core"

    # Model does have objects...
    queryset = IntervalSchedule.objects.all()
    serializer_class = IntervalScheduleSerializer


class PeriodicTaskSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes periodic tasks.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:periodictask-detail"
    )
    display_name = serializers.SerializerMethodField("do_display_name")
    display_schedule = serializers.SerializerMethodField("do_display_schedule")

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
        view_name="blueflow:intervalschedule-detail",
    )
    crontab = serializers.HyperlinkedRelatedField(
        required=False,
        queryset=CrontabSchedule.objects.all(),
        view_name="blueflow:crontabschedule-detail",
    )

    def validate(self, attrs):
        """Exactly one of (interval, crontab) is required.

        Django REST API documentation on validators:
        http://www.django-rest-framework.org/api-guide/validators/
        """
        if (
            self.context["request"].method == "PATCH"
            and "interval" not in attrs
            and "crontab" not in attrs
        ):
            return attrs
        if not bool("interval" in attrs) ^ bool("crontab" in attrs):
            raise serializers.ValidationError(
                "Exactly one of (interval, crontab) is required"
            )
        return attrs

    class Meta:
        model = PeriodicTask
        # NOTE HHolm 2017-08-29: I think most of these args are in fact
        #   read-only.  We should consider tagging them as such.
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
            "display_name",
            "display_schedule",
        ]


class PeriodicTaskFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    class Meta:
        model = PeriodicTask

        fields = {
            "name": ["exact"],
            "task": ["exact"],
        }


class PeriodicTaskViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Periodic task."""

    waffle_switch = "core"

    queryset = PeriodicTask.objects.all()
    serializer_class = PeriodicTaskSerializer

    search_fields = ["name"]
    filterset_class = PeriodicTaskFilter
