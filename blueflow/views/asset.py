"""ViewSet for assets."""

import logging

import django_filters
import django_filters.rest_framework.filters as drf_filters
import netfields
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from simple_history import utils as hist_utils

from blueflow import models, serializers

from . import utils

logger = logging.getLogger(__name__)


class AssetFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    date_range = django_filters.DateRangeFilter(field_name="created")
    datetime_range = django_filters.DateTimeFromToRangeFilter(field_name="created")
    network = django_filters.NumberFilter(method="filter_network")
    no_network = drf_filters.BooleanFilter(method="filter_no_network")
    group = django_filters.NumberFilter(field_name="groups")
    tag = django_filters.NumberFilter(field_name="tags")

    @staticmethod
    def filter_network(queryset: QuerySet, name: str, value: int) -> QuerySet:
        """Get assets that belong to a certain network."""
        if name != "network":
            _msg = f"Unexpected filter name: {name!r}"
            raise ValueError(_msg)
        return queryset.in_network(network_id=value)

    @staticmethod
    def filter_no_network(queryset: QuerySet, name: str, value: bool) -> QuerySet:  # noqa: FBT001
        """Get assets that belong to no network."""
        if name != "no_network":
            _msg = f"Unexpected filter name: {name!r}"
            raise ValueError(_msg)
        if value is not True:
            # This is sliiightly iffy.  The user might expect to see the
            # assets that *do* belong to a network.  Oh well.
            return queryset
        return queryset.no_network()

    class Meta:
        """Wire this filter to a model."""

        model = models.Asset

        # The first lookup in each field will be used as the default by
        # autocomplete.py.  "icontains" is usually a good choice.
        #
        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields = {  # noqa: RUF012
            "hostname": ["icontains"],
            "oui_manufacturer": ["icontains"],
            "category": ["icontains", "exact"],
            "id": ["in"],
            "serial_number": ["istartswith", "iexact", "isnull"],
            "name": ["icontains", "exact"],
            "os": ["istartswith", "icontains", "iexact", "exact", "isnull"],
            "owner": ["icontains", "exact"],
            "manufacturer": [
                "istartswith",
                "icontains",
                "iregex",
                "iexact",
                "exact",
                "isnull",
            ],
            "model": [
                "istartswith",
                "icontains",
                "iregex",
                "iexact",
                "exact",
                "isnull",
            ],
            "tag_number": ["icontains"],
            "udi": ["istartswith", "iexact"],
            "tags__name": ["istartswith"],
        }
        filter_overrides = {  # noqa: RUF012
            netfields.InetAddressField: {
                "filter_class": django_filters.Filter,
            },
            netfields.MACAddressField: {
                "filter_class": django_filters.Filter,
            },
        }


class AssetViewSet(
    utils.PaginateRelationsMixin,
    viewsets.ModelViewSet,
):
    """API endpoint for an Asset (representing a networked device).

    read: Return the given asset.

    See additional methods:
    `/fields`
    `/history`
    `/networks`
    `/scans`
    `/similar`

    list: Return a list of assets.

    Additional methods:
    `/bulk_update` — PATCH a list of assets by id (partial updates)
    `/duplicate_ips`
    `/histogram`
    `/upsert`

    In addition, there are several filtering and search terms available.

    create: Create a new asset
    delete: Delete the given asset
    update: Modify the given asset
    partial_update: Modify the given asset
    """

    # NOTE: Order of mixins/base class is important!  Mixins that override
    #   methods *must come first* in order to properly override.  This is
    #   counterintuitive... but it's the way it is.  (Assiduous use of
    #   inspect.getmro() reveals that this is indeed the case.)

    # Known N+1 problems on the list endpoint.
    #
    # AssetSerializer fans out additional queries per-asset for several
    # related fields. Each of these scales linearly with page size and,
    # combined with HugeLimitOffsetPagination's 1,000,000 default limit,
    # can produce pathological query counts on /api/assets/.
    #
    # Fields currently causing per-asset fan-out (review for removal from
    # the list response or for prefetch_related):
    #   - asset_tags             (nested AssetTagSerializer, many=True;
    #                             reverse FK to AssetTag through-model)
    #
    # Only `usage` is currently prefetched (see test_asset_list_usage_does_
    # not_n_plus_one). The remaining relations above are unaddressed.
    queryset = (
        models.Asset.objects.prefetch_related("usage")
        .prefetch_related("request_senders__request")
        .prefetch_related("request_receivers__request")
        .prefetch_related("interface")
    )
    serializer_class = serializers.AssetRequestSerializer

    # Documentation on search filters:
    # http://www.django-rest-framework.org/api-guide/filtering/
    #
    # By default, searches will use case-insensitive partial matches. The
    # search parameter may contain multiple search terms, which should be
    # whitespace and/or comma separated. If multiple search terms are used
    # then objects will be returned in the list only if all the provided terms
    # are matched, in other words, 'AND'.
    search_fields = (
        "hostname",
        "manufacturer",
        "model",
        "name",
        "oui_manufacturer",
        "os",
        "owner",
        "serial_number",
        "tag_number",
        "tags__name",
        "udi",
    )
    filterset_class = AssetFilter

    def retrieve(self, *args, **kwargs) -> Response:
        self.serializer_class = serializers.AssetResponseSerializer
        response = super().retrieve(*args, **kwargs)
        return response

    def list(self, *args, **kwargs) -> Response:
        self.serializer_class = serializers.AssetResponseSerializer
        response = super().list(*args, **kwargs)
        return response

    def create(self, *_, **__) -> Response:
        return Response(status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["PATCH"])
    def bulk_update(self, request: Request) -> Response:
        """Perform partial updates on multiple assets in a single request.

        Accepts a list of partial asset payloads. Each item must include an
        ``id`` field identifying the asset to update. Only the fields provided
        are modified; all other fields are left unchanged.

        Returns a list of updated asset objects. If any ``id`` is not found a
        404 response is returned immediately.

        Example request body::

            [
                {"id": 1, "hostname": "device-a.local"},
                {"id": 2, "ip_address": "10.0.0.5", "os": "Linux"}
            ]
        """
        # Validate the batch envelope (list shape, id presence, id uniqueness)
        # through DRF's standard ValidationError pathway.
        envelope = serializers.AssetUpdateSerializer(data=request.data, many=True)
        envelope.is_valid(raise_exception=True)

        # Phase 1: resolve + validate every item before touching the DB. The
        # id-to-instance lookup is a 404 (a missing resource, not a client-side
        # validation failure), so it stays here rather than in the serializer.

        # Further, trying to tie this to a ModelSerializer bumps into DRF's
        # uniquenessserializer. The work around is to validate through
        # the list serializer and ignore the validated fields
        validated: list[serializers.AssetRequestSerializer] = []
        for item in request.data:
            asset_id = item["id"]
            try:
                asset = models.Asset.objects.get(pk=asset_id)
            except models.Asset.DoesNotExist:
                return Response(
                    {"detail": f"Asset with id={asset_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = self.get_serializer_class()(
                asset, data=item, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            validated.append(serializer)

        # Phase 2: commit all updates atomically — all succeed or none do.
        with transaction.atomic():
            results = [serializer.save() for serializer in validated]

        return Response(
            serializers.AssetResponseSerializer(
                results, many=True, context={"request": request}
            ).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["PUT"])
    def upsert(self, request: Request) -> Response:
        """Create or update an Asset by MAC address.

        Intended for passive scanners (e.g. Tapirx) that discover assets from
        network traffic and identify them by MAC address rather than server ID.

        The input is a JSON blob containing any Asset field; ``mac_address`` is
        required.  Returns 201 on creation, 200 on update.

        For batch partial-updates of assets with known IDs, use
        ``PATCH /api/assets/bulk_update/`` instead.
        """
        serializer = serializers.AssetUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        created = False
        mac_address = validated.pop("mac_address")
        new_services = validated.pop("services", [])
        ip = validated.pop("ip_address", None)
        with transaction.atomic():
            try:
                asset = models.Asset.objects.get(interface__mac_address=mac_address)
                for k, v in validated.items():
                    setattr(asset, k, v)
                asset.save()
            except models.Asset.DoesNotExist:
                created = True
                asset = models.Asset.objects.create(**validated)
            ips = [ip] if ip is not None else None
            asset.add_or_update_interface(mac_address=mac_address, ips=ips)
            for service in new_services:
                asset.add_service(service["port"], service["protocol"])

        # TODO(taylorcochran): timestamp is server-derived (timezone.now()) at
        #   the call site today. Switch to network-derived time from the
        #   upserted asset payload once scanners reliably provide it.
        asset.update_usage(timezone.now())

        # Record history change reason from scanner metadata
        last_seen = request.data.get("last_seen") or timezone.now()
        client_id = request.data.get("client_id") or "observer"
        provenance = request.data.get("provenance") or "Data"
        reason = f"{provenance} seen by {client_id} at {last_seen}"
        try:
            hist_utils.update_change_reason(asset, reason)
        except AttributeError:
            record = asset.history.order_by("-history_date").first()
            if record is not None:
                record.__class__.objects.filter(pk=record.pk).update(
                    history_change_reason=reason
                )
            else:
                logger.debug(
                    "Could not set history_change_reason for asset pk=%s", asset.pk
                )
        serializer = serializers.AssetResponseSerializer(
            asset, context={"request": request}
        )
        response = Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
        return response
