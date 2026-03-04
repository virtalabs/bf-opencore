"""ViewSets for Pulse feed."""

import logging

import django_filters
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import PulseFeedItem

from .utils import PaginateRelationsMixin
from .vulnerability import VulnerabilitySerializer

logger = logging.getLogger(__name__)


class PulseFeedItemSerializer(serializers.HyperlinkedModelSerializer):
    """Serialize Pulse feed items."""

    url = serializers.HyperlinkedIdentityField(
        view_name="bf_opencore:pulsefeeditem-detail",
        lookup_field="external_pulse_id",
    )

    vulnerabilities = VulnerabilitySerializer(read_only=True, many=True)

    class Meta:
        """Wire up serializer to model."""

        # We need access to the _meta field

        model = PulseFeedItem
        model_fields = tuple(f.name for f in model._meta.fields)
        computed_fields = (
            "url",
            "last_notes_editor",
            "last_notes_date",
            "vulnerabilities",
        )
        fields = model_fields + computed_fields


class PulseFeedItemFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    # Few public methods; that's just how django-filters work

    status__ne = django_filters.CharFilter("status", exclude=True)

    class Meta:  # noqa
        model = PulseFeedItem
        fields = {
            "status": ["exact"],
        }


class PulseFeedItemViewSet(WaffleSwitchMixin, PaginateRelationsMixin, viewsets.ModelViewSet):
    """View Pulse feed items."""

    waffle_switch = "core"

    # yes, there are objects
    queryset = PulseFeedItem.objects.order_by("-date_last_updated")
    lookup_field = "external_pulse_id"

    serializer_class = PulseFeedItemSerializer
    filterset_class = PulseFeedItemFilter

    def destroy(self, request, *args, **kwargs):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("Deleting pulse feed items is not allowed.")

    @action(detail=False)
    def closed_by_quarter(self, request):
        """Return a list of `closed` feed items for past quarters.

        Parameters
        ----------
         - `quarters`: number of quarters, including the current quarter, for
           which to fetch data.

        """
        quarters = request.GET.get("quarters")
        if quarters is not None:
            try:
                nquarters = int(quarters)
            except ValueError:
                return Response(status=status.HTTP_400_BAD_REQUEST)

        qtr_starts = []
        ser_data = []
        qtr_data = PulseFeedItem.objects.closed_quarterly(nquarters)
        for qtr_start, qtr in qtr_data:
            qtr_starts.append(qtr_start)
            serializer = PulseFeedItemSerializer(qtr, many=True,
                                                 context={"request": request})
            ser_data.append(serializer.data)

        response = {
            "count": len(ser_data),
            "qtr_starts": qtr_starts,
            "feed_items": ser_data,
        }
        return Response(response)
