"""ViewSet for alerts."""

import logging
from django.urls import reverse_lazy
from django.utils import timezone
from rest_framework import viewsets, serializers
from waffle.mixins import WaffleSwitchMixin
from bf_opencore.models import Alert

logger = logging.getLogger(__name__)


class AlertSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes alerts.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    # Few public methods; that's just how serializers work

    # Since we namespace with `api:` we have to specify the view-name.
    url = serializers.HyperlinkedIdentityField(
        view_name="api:alert-detail")
    asset = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name="blueflow:asset",
    )
    connector = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name="blueflow:connector",
    )
    connectortask = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name="blueflow:connectortask",
    )
    pulsefeeditem = serializers.SerializerMethodField()
    riskmetrics = serializers.HyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name="api:riskmetrics-detail",
    )
    vulnerability = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name="blueflow:vulnerability",
    )

    class Meta:  # noqa
        model = Alert

        # Fields defined in the schema
        asset_fields = tuple(f.name for f in model._meta.fields)

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            'url',
            'asset',
            'link',
            'connector',
            'connectortask',
            'pulsefeeditem',
            'riskmetrics',
            'vulnerability',
            'status',
            'display_text',
        )

        fields = asset_fields + computed_fields

    def get_pulsefeeditem(self, obj):
        """Get the URL of the Pulse page, if applicable."""
        if obj.pulsefeeditem is None:
            return None
        return reverse_lazy('blueflow:pulse', args=[
            obj.pulsefeeditem.external_pulse_id])

    def update(self, instance, validated_data):
        """Update date_read upon any PATCH request.

        Django REST Framework documentation:
        http://www.django-rest-framework.org/api-guide/serializers/#saving-instances
        """
        if not instance.date_read:
            instance.date_read = timezone.now()
            instance.save()
        return super().update(instance, validated_data)


class AlertViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """Alert."""

    waffle_switch = "legacy"

    # Alert model does have 'objects'

    queryset = Alert.objects.\
        exclude(date_expiration__lt=timezone.now()).\
        order_by('-date_created')
    serializer_class = AlertSerializer

    def list(self, request, *args, **kwargs):
        """Add additional counts to list view.

        NOTE: if this function changes, you might also need to change code in
        blueflow/models/alert.py::Alert::status().

        Based on this stackoverflow post:
        https://stackoverflow.com/questions/24164160/adding-extra-data-to-django-rest-framework-results-for-entire-result-set
        """
        count_unread = self.queryset.\
            filter(date_read__isnull=True).\
            count()
        count_read = self.queryset.\
            filter(date_read__isnull=False).\
            count()
        response = super().list(request, args, kwargs)
        response.data['count_unread'] = count_unread
        response.data['count_read'] = count_read
        return response
