"""ViewSet for assets."""

import importlib
import logging
from typing import ClassVar

import django_filters
import django_filters.rest_framework.filters as drf_filters
import netfields
from django.core import exceptions as d_ex
from django.db import transaction
from django.db.models import Case, Count, QuerySet, When
from django.db.models.aggregates import Func
from django.db.utils import IntegrityError
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from simple_history import utils as hist_utils
from waffle.mixins import WaffleSwitchMixin

from blueflow import models

from . import assettag, utils

logger = logging.getLogger(__name__)


class JSONChild(Func):
    """Extract a named child of a JSONField.

    Because this is a Func, its result can be used for order_by, as opposed
    to specifying '-jsonfieldname__field' or similar, which doesn't work.
    """

    # not bothering to override __and__, __or__, __rand__, __ror__
    function = "#>"
    template = "%(expressions)s%(function)s'{%(path)s}'"
    arity = 1

    def __init__(self, expression: str, path: str) -> None:
        """Form an expression and plug the path argument into the template."""
        super().__init__(expression, path=path)


class AssetServiceSerializer(serializers.Serializer):
    """A single ``(port, protocol)`` observation on an asset.

    Wire shape matches the topology schema's ``services[]`` element.
    """

    port = serializers.IntegerField(
        min_value=models.PORT_MIN, max_value=models.PORT_MAX
    )
    protocol = serializers.CharField(
        min_length=1,
        max_length=models.PROTOCOL_MAX_LENGTH,
        allow_blank=False,
    )


class AssetUpsertSerializer(serializers.Serializer):
    """Input serializer for PUT /api/assets/upsert/.

    Validates scanner payloads before create-or-update.
    Only includes fields that passive scanners are expected to send.
    """

    mac_address = serializers.CharField(required=True, allow_blank=False)
    ip_address = serializers.IPAddressField(
        required=False, allow_blank=False, allow_null=True
    )
    name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    hostname = serializers.CharField(required=False, allow_blank=False, allow_null=True)
    manufacturer = serializers.CharField(
        required=True, allow_blank=False, allow_null=False
    )
    model = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    serial_number = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    os = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    app_sw_version = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    device_class = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    external_keys = serializers.JSONField(required=False, allow_null=True)
    services = AssetServiceSerializer(many=True, required=False)

    def validate(self, attrs: dict) -> dict:
        """Map TapirXL ``device_class`` to ``category`` when Vector is bypassed."""
        device_class = attrs.pop("device_class", None)
        if device_class and not attrs.get("category"):
            attrs["category"] = device_class
        return attrs

    def validate_services(
        self, services: list[dict[str, int | str]]
    ) -> list[dict[str, int | str]]:
        """Deduplicate ``(port, protocol)`` pairs."""
        seen: set[tuple[int, str]] = set()
        deduped: list[dict[str, int | str]] = []
        for s in services:
            key = (s["port"], s["protocol"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(s)
        return deduped


# Usage field schema. Index follows Python's datetime.weekday() / ISO 8601:
# 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday.
# Each entry maps hour-of-day (0-23, JSON-string-coerced) to non-negative count.
# Hours with zero observations are omitted. The schema is inlined here (rather
# than a named Usage component) because it's small and used in exactly one place.
_USAGE_FIELD_SCHEMA = {
    "type": "array",
    "minItems": 7,
    "maxItems": 7,
    "items": {
        "type": "object",
        "additionalProperties": {"type": "integer", "minimum": 0},
    },
    "example": [
        {"9": 1, "10": 12, "11": 8, "14": 3, "15": 5},  # 0 = Monday
        {"9": 1, "10": 8, "11": 15},  # 1 = Tuesday
        {"9": 2, "14": 5},  # 2 = Wednesday
        {"10": 6, "11": 9, "13": 4},  # 3 = Thursday
        {"9": 1, "13": 2},  # 4 = Friday
        {},  # 5 = Saturday
        {},  # 6 = Sunday
    ],
}


class AssetSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes assets.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="blueflow:asset-detail")
    tags_url = serializers.HyperlinkedIdentityField(view_name="blueflow:asset-tags")
    scans_url = serializers.HyperlinkedIdentityField(view_name="blueflow:asset-scans")

    asset_tags = assettag.AssetTagSerializer(read_only=True, many=True)
    display_name = serializers.CharField(
        max_length=126, allow_blank=True, allow_null=True, required=False
    )

    last_updated = serializers.DateTimeField(read_only=True, allow_null=True)

    usage = serializers.SerializerMethodField(
        help_text=(
            "Usage pattern: 7-element array of hour-of-day to observation-count "
            "maps. Index is 0-based with Monday first — 0=Monday, 1=Tuesday, "
            "2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday. Hour keys "
            "are JSON-string-coerced integers 0-23; counts are non-negative; "
            "hours with zero observations are omitted from the response."
        ),
    )
    manufacturer = serializers.CharField()

    class Meta:
        """Wire this serializer to a model."""

        model = models.Asset

        # Fields defined in the schema
        asset_fields = tuple(f.name for f in model._meta.fields)  # noqa: SLF001

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            "url",
            "tags_url",
            "scans_url",
            "display_name",
            "last_updated",
            "asset_tags",
            "usage",
            "cpe",
        )

        fields = asset_fields + computed_fields

        read_only_fields: ClassVar = ["oui_manufacturer"]

    def validate_ip_address(self, ip_string: str) -> str:
        """Reject empty IP address strings."""
        if ip_string == "":
            msg = "ip_address must not be empty."
            raise serializers.ValidationError(msg)
        return ip_string

    def validate_mac_address(self, mac_string: str) -> str:
        """Reject empty MAC address strings."""
        if mac_string == "":
            msg = "mac_address must not be empty."
            raise serializers.ValidationError(msg)
        return mac_string

    @extend_schema_field(_USAGE_FIELD_SCHEMA)
    def get_usage(self, obj):
        days = [{} for _ in range(7)]
        for usage in obj.usage.all():
            bucket = days[usage.day_of_week]
            for hour in range(24):
                count = getattr(usage, f"hour_{hour:02d}")
                if count > 0:
                    bucket[str(hour)] = count
        return days


class HistoricalAssetSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes asset history."""

    history_user = serializers.HyperlinkedRelatedField(
        view_name="blueflow:user-detail",
        read_only=True,
    )

    class Meta:
        """Wire this serializer to a model."""

        model = models.Asset.history.model
        # Fields that are unique to the historical model (Should maybe
        # compute these too?  It could be done with a set difference...)
        historical_fields = (
            "history_change_reason",
            "history_date",
            "history_id",
            "history_type",
            "history_user",
            "history_user_id",
        )
        fields = AssetSerializer.Meta.asset_fields + historical_fields


# Why does this exist?
class ChangeLogMetaclass(type(AssetSerializer)):
    """Metaclass for creating the ChangeLogAssetSerializer.

    NOTE: this is double-plus deep magic, since this metaclass has to
    inherit from the serializers' metaclass!  (Usually, a metaclass
    simply inherits from `type`.)  We accomplish this with the
    type(AssetSerializer) ("what is the metaclass for AssetSerializer").
    """

    def __new__(mcs, name: str, parents: tuple, dct: dict) -> "ChangeLogMetaclass":
        """Create the ChangeLogAssetSerializer class."""
        if "Meta" in dct:
            # NOTE: the changed fields are supposed to be the same as in
            #   AssetSerializer.Meta.asset_fields -- except for 'id'
            #   (which will never change)
            changed_fields = getattr(dct["Meta"], "changed_fields", ())
            for field in changed_fields:
                field_chgd = field + "__changed"
                if field == "id":
                    continue
                if field in ["ip_address", "mac_address"]:
                    # ip and mac addresses are special: they cannot
                    # directly be serialized as JSON so we have to treat
                    # them as if they were strings in order to
                    # serialize.
                    dct[field] = serializers.CharField(source=field_chgd)
                else:
                    dct[field] = serializers.ReadOnlyField(source=field_chgd)
        return super().__new__(mcs, name, parents, dct)


class ChangeLogAssetSerializer(
    serializers.HyperlinkedModelSerializer, metaclass=ChangeLogMetaclass
):
    """Almost like HistoricalAssetSerializer.

    but used to only return the "changed" fields.
    """

    history_user = serializers.HyperlinkedRelatedField(
        view_name="blueflow:user-detail",
        read_only=True,
    )

    class Meta:
        """Wire this serializer to a model."""

        model = models.Asset.history.model
        changed_fields = AssetSerializer.Meta.asset_fields
        fields = changed_fields + HistoricalAssetSerializer.Meta.historical_fields


class AssetFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    date_range = django_filters.DateRangeFilter(field_name="created")
    datetime_range = django_filters.DateTimeFromToRangeFilter(field_name="created")
    network = django_filters.NumberFilter(method="filter_network")
    no_network = drf_filters.BooleanFilter(method="filter_no_network")
    unassessed = drf_filters.BooleanFilter(method="filter_unassessed")
    assessed_factor = drf_filters.NumberFilter(method="filter_assessed_factor")
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

    @staticmethod
    def filter_unassessed(queryset: QuerySet, _name: str, _value: bool) -> QuerySet:  # noqa: FBT001
        """Get assets that lack AssetRiskFactors.

        Calling with value False is a silly double negative ("not unassessed").
        """
        # TODO(taylorcochran): Implement unassessed
        _msg = "Unassessed is not implemented"
        raise NotImplementedError(_msg)

    @staticmethod
    def filter_assessed_factor(queryset: QuerySet, _name: str, value: int) -> QuerySet:
        """Get assets that have or lack a *particular* RiskFactor.

        To find assets that *have* a particular RiskFactor n, query with
        assessed_factor=n.

        To find assets that *lack* a particular RiskFactor n, query with
        assessed_factor=-n.
        """
        # TODO(taylorcochran): Implement assessed_factor
        _msg = "Assessed factor is not implemented"
        raise NotImplementedError(_msg)

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
            # TODO(taylorcochran): Add risk score filters
            "id": ["in"],
            "ip_address": [
                "istartswith",
                "exact",
                "net_contained",
                "net_contained_or_equal",
                "isnull",
            ],
            "mac_address": ["istartswith", "lt", "lte", "gte", "gt", "isnull"],
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
    WaffleSwitchMixin,
    utils.ChangeReasonMixin,
    utils.PaginateRelationsMixin,
    viewsets.ModelViewSet,
):
    """API endpoint for an Asset (representing a networked device).

    read: Return the given asset.

    See additional methods:
    `/changelog`
    `/fields`
    `/history`
    `/needs_sw_update`
    `/networks`
    `/scans`
    `/similar`
    `/tags`

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

    waffle_switch = "core"

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
    queryset = models.Asset.objects.prefetch_related("usage").prefetch_related(
        "port_protocols__port_protocol"
    )
    serializer_class = AssetSerializer

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
        "ip_address",
        "mac_address",
        "manufacturer",
        "model",
        "name",
        "oui_manufacturer",
        "os",
        "owner",
        "serial_number",
        "tag_number",
        "tags__name",
        # The following field would enable search on custom field *name*
        "udi",
    )
    filterset_class = AssetFilter

    def get_renderer_context(self) -> dict:
        """If caller specifies fields, then set the CSV header accordingly.

        If not, use a default set.
        """
        default_headers = [
            "id",
            "name",
            "display_name",
            "hostname",
            "owner",
            "ip_address",
            "mac_address",
            "oui_manufacturer",
            "manufacturer",
            "model",
            "os",
            "app_sw_version",
            "serial_number",
            "tag_number",
            "category",
            "created",
            "udi",
        ]
        context = super().get_renderer_context()
        if "fields" in self.request.GET:
            context["header"] = self.request.GET["fields"].split(",")
        else:
            context["header"] = default_headers
        return context

    ################################
    # Detail methods/actions

    @extend_schema(exclude=True)
    @action(detail=True)
    def changelog(self, request: Request, _pk: int) -> Response:
        """Like full history but fields are null except the one that changed.

        NOTE: not paginated, while the history is.
        """
        # The lack of pagination is due to the LAG window function that
        # forms the basis of the ChangeLog -- it may not be used inside
        # a GROUP BY (which apparently is an ingredient in the
        # pagination.)

        asset = self.get_object()
        qset = asset.changelog_qset()
        serializer = ChangeLogAssetSerializer(
            qset, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(exclude=True)
    @action(detail=True)
    def fields(self, request: Request, pk: int) -> Response:
        """List fields for an Asset.

        Technically all assets will have the same fields.  But there's
        some info about fields that may be individual (e.g., is the
        field populated.)  Thus we display it via the individual asset
        route, not the 'list' route.

        To include "related fields", pass the query parameter 'relations'.
        """
        # NOTE: according to Django documentation & code/implementation,
        #   _meta.fields is unsupported.  We should use _meta.get_fields()

        # Default behaviour: Don't include relations/related fields, as these
        # incur joins.
        relations = request.query_params.get("relations", "false")
        include_relations = relations.lower()[:1] in ["", "1", "t"]

        fields = []
        for f in models.Asset._meta.get_fields():  # noqa: SLF001
            if f.is_relation and not include_relations:
                continue
            if hasattr(f, "deconstruct"):
                dec = f.deconstruct()
            else:
                dec = (f.name, f.__class__.__name__, [], {})
            name = dec[0]
            verbose_name = dec[3].get("verbose_name")

            fields.append(
                {
                    "name": name,
                    "display_name": (
                        verbose_name
                        if verbose_name is not None
                        else name.replace("_", " ").capitalize()
                    ),
                    "field_type": dec[1],
                    "is_relation": f.is_relation,  # Foreign keys, reverses, etc.
                    "is_custom": False,
                }
            )

        for f in models.AssetCustomFieldName.objects.all():
            name = f.field_name
            cfv = models.AssetCustomField.objects.filter(asset_id=pk, field=f).first()
            fields.append(
                {
                    "name": name,
                    "display_name": name.replace("_", " ").capitalize(),
                    "field_type": f.display_type,
                    "is_relation": False,
                    "is_custom": True,
                    "custom_field_id": cfv.pk if cfv else None,
                }
            )

        return Response(
            {
                "count": len(fields),
                "results": fields,
            }
        )

    @extend_schema(exclude=True)
    @action(detail=True)
    def history(self, request: Request, _pk: int) -> Response:
        """Full history of asset (paginated).

        Or, if a `field=<field_name>` query argument is given, returns
        only the history records where that field changed.  (In this
        case it's not paginated.)
        """
        if not request.query_params:
            # Full history
            qset = self.get_object().history_qset()
            return self.paginate_relations(request, qset, "HistoricalAssetSerializer")
        # History for a single field
        field_name = request.query_params.get("field")
        if field_name is None:
            raise serializers.ValidationError(
                {
                    "field": (
                        f"User supplied query parameters '{request.query_params}'"
                        " that did not include a field value"
                    )
                }
            )
        try:
            rqset = self.get_object().field_history_rqset(field_name, newest_first=True)
        except d_ex.FieldDoesNotExist as err:
            raise serializers.ValidationError(
                {"field": f"User tried to query for nonexistent field '{field_name}'"}
            ) from err
        serializer = HistoricalAssetSerializer(
            rqset, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(exclude=True)
    @action(detail=True)
    def needs_sw_update(self, _request: Request, _pk: int) -> Response:
        """Return whether this asset needs a software update.

        @returns:
            {needs_update: bool  # needs an update
             latest: string      # latest version number
             versions_in_use: dict<string -> int>}  # count other versions
        """
        asset = self.get_object()
        needs_update, latest, vcounts = asset.needs_sw_update()
        resp = {
            "needs_update": needs_update,
            "latest": latest,
            "versions_in_use": vcounts,
        }
        return Response(resp)

    @extend_schema(exclude=True)
    @action(detail=True)
    def networks(self, request: Request, _pk: int) -> Response:
        """Networks that this asset belongs to."""
        # FUTURE: Replace with /api/networks/?asset=<pk>

        qset = self.get_object().network_qset()
        return self.paginate_relations(request, qset, "NetworkSerializer")

    @extend_schema(exclude=True)
    @action(detail=True)
    def scans(self, request: Request, _pk: int) -> Response:
        """Return scans of the asset."""
        # FUTURE: Replace with /api/scans/?asset=<pk>

        scan_qset = self.get_object().scan_qset()
        return self.paginate_relations(request, scan_qset, "ScanSerializer")

    @extend_schema(exclude=True)
    @action(detail=True)
    def similar(self, request: Request, _pk: int) -> Response:
        """Similar assets."""
        exclude_self = True
        if request.query_params.get("exclude_self") in ("false", "0"):
            exclude_self = False

        # This stuff might not be necessary.  The DRF pagination system
        # might take care of it (since it's the same serializer etc.
        qset = self.get_object().similar_qset(exclude_self=exclude_self)
        # TODO(taylorcochran): Add risk score ordering
        return self.paginate_relations(request, qset, "AssetSerializer")

    @extend_schema(exclude=True)
    @action(detail=True, methods=["GET", "POST"])
    def tags(self, request: Request, _pk: int) -> Response | None:
        """Tags attached to the asset."""
        asset = self.get_object()
        if request.method == "GET":
            # FUTURE: Replace with /api/tags/?asset=<pk>
            tag_qset = asset.tag_qset()
            return self.paginate_relations(request, tag_qset, "TagSerializer")
        if request.method == "POST":
            tag_id = request.data.get("tag_id")
            if tag_id is None:
                raise serializers.ValidationError(
                    {
                        "tag_id": ["'tag_id' is required"],
                    }
                )
            try:
                tag = models.Tag.objects.get(pk=tag_id)
            except d_ex.ObjectDoesNotExist as err:
                raise serializers.ValidationError(
                    {
                        "tag_id": [f"Tag does not exist: id={tag_id}"],
                    }
                ) from err
            asset_tag = models.AssetTag(asset=asset, tag=tag, provenance="API")
            try:
                asset_tag.save()
                response_status = status.HTTP_201_CREATED
                logger.debug(
                    "Created new asset-tag link between %s and %s: %s",
                    asset,
                    tag,
                    asset_tag,
                )
            except IntegrityError:
                asset_tag = models.AssetTag.objects.get(asset=asset, tag=tag)
                response_status = status.HTTP_200_OK
                logger.debug(
                    "Asset-tag link between %s and %s already existed: %s",
                    asset,
                    tag,
                    asset_tag,
                )
            views = importlib.import_module("blueflow.views")
            serializer = views.TagSerializer(tag, context={"request": request})
            return Response(serializer.data, status=response_status)

        return None

    ################################
    # List methods/actions

    @extend_schema(exclude=True)
    @action(detail=False)
    def duplicate_ips(self, _request: Request) -> Response:
        """Return set of duplicate IP addresses and their counts."""
        assets = self.filter_queryset(self.get_queryset())
        qset = (
            assets.values("ip_address")
            .annotate(howmany=Count("ip_address"))
            .filter(howmany__gte=2)
            .order_by("-howmany")
        )
        resp = [(str(x["ip_address"]), x["howmany"]) for x in qset]
        return Response(resp)

    @extend_schema(exclude=True)
    @action(detail=False)
    def histogram(self, request: Request) -> Response:
        """Return an optionally filtered histogram over an asset field.

        Returns a list of {field_name: xxx, count: N} objects.
        """
        field_name = request.query_params.get("field")
        if field_name is None:
            raise serializers.ValidationError({"field": "Missing field name"})

        try:
            limit = int(request.query_params.get("limit", 0))
        except ValueError as err:
            raise serializers.ValidationError({"limit": "Invalid limit"}) from err

        include_null = request.query_params.get("nulls", "").lower() in (
            "true",
            "yes",
            "1",
        )

        # apply any asset filters such as 'manufacturer__iexact'
        assets = self.filter_queryset(self.get_queryset())

        try:
            if include_null:
                # by default django won't count nulls; this one weird trick
                # makes it do so.  basically, count 1 if field is not null, and
                # 1 otherwise.
                params = {field_name + "__isnull": False, "then": 1}
                results = assets.values(field_name).annotate(
                    count=Count(Case(When(**params), default=1))
                )
            else:
                params = {field_name + "__isnull": True, field_name: ""}
                assets = assets.exclude(**params)
                results = assets.values(field_name).annotate(count=Count(field_name))

        except d_ex.FieldError as err:
            raise serializers.ValidationError(
                {"field": f"Invalid field name '{field_name}'"}
            ) from err
        results = results.order_by("-count")
        if limit > 0:
            results = results[:limit]
        return Response(results)

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
        if not isinstance(request.data, list):
            return Response(
                {"detail": "Expected a list of objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Phase 1: normalise and validate every item before touching the DB.
        validated: list[tuple[models.Asset, AssetSerializer]] = []
        seen_ids: set[int] = set()
        for item in request.data:
            asset_id = item.get("id")
            if asset_id is None:
                return Response(
                    {"detail": "Each item must include an 'id' field."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if asset_id in seen_ids:
                return Response(
                    {"detail": f"Duplicate id in request: {asset_id}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen_ids.add(asset_id)

            try:
                asset = models.Asset.objects.get(pk=asset_id)
            except models.Asset.DoesNotExist:
                return Response(
                    {"detail": f"Asset with id={asset_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = AssetSerializer(
                asset, data=item, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            validated.append((asset, serializer))

        # Phase 2: commit all updates atomically — all succeed or none do.
        with transaction.atomic():
            results = [serializer.save() for _asset, serializer in validated]

        return Response(
            AssetSerializer(results, many=True, context={"request": request}).data,
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
        serializer = AssetUpsertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        # Reject if the proposed hostname is already owned by a different MAC.
        # Same-MAC reuse (a legitimate update) falls through; missing/null
        # hostname falls through. Empty strings are blocked by the serializer.
        proposed_hostname = validated.get("hostname")
        if proposed_hostname:
            conflict = (
                models.Asset.objects.filter(hostname=proposed_hostname)
                .exclude(mac_address=validated["mac_address"])
                .first()
            )
            if conflict is not None:
                return Response(
                    {
                        "hostname": [
                            f"Hostname '{proposed_hostname}' is already used by "
                            f"asset id={conflict.id}.",
                        ],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        created = False
        mac_address = validated.pop("mac_address")
        new_services = validated.pop("services", [])
        with transaction.atomic():
            try:
                asset = models.Asset.objects.get(mac_address=mac_address)
                for k, v in validated.items():
                    setattr(asset, k, v)
                asset.save()
            except models.Asset.DoesNotExist:
                created = True
                asset = models.Asset.objects.create(
                    mac_address=mac_address, **validated
                )
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
        serializer = AssetSerializer(asset, context={"request": request})
        response = Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
        return response
