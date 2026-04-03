"""ViewSet for assets."""

import importlib
import logging
import re
from typing import Any, ClassVar

import django_filters
import django_filters.rest_framework.filters as drf_filters
import netfields
from django.core import exceptions as d_ex
from django.db import transaction
from django.db.models import Case, Count, QuerySet, When
from django.db.models.aggregates import Func
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework_csv import renderers as drf_csv_renderers
from simple_history import utils as hist_utils
from waffle.mixins import WaffleSwitchMixin

from blueflow.models import (
    Asset,
    AssetCustomField,
    AssetCustomFieldName,
    AssetTag,
    AssetVulnerability,
    PulseFeedItem,
    Tag,
)

from .asset_custom_field import AssetCustomFieldSerializer
from .assettag import AssetTagSerializer
from .utils import ChangeReasonMixin, PaginateRelationsMixin

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


class MiniAssetVulnerabilitySerializer(serializers.HyperlinkedModelSerializer):
    """Lightweight shallow AssetVulnerability serializer.

    Exists so that we can show the status of AssetVulnerabilities, but not
    their details, in serialized assets.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:assetvulnerability-detail"
    )

    class Meta:
        """Wire this serializer to a model."""

        model = AssetVulnerability
        fields = (
            "id",
            "vulnerability_id",
            "date_added",
            "date_remediated",
            "date_ignored",
            "provenance",
            "url",
        )


class AssetSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes assets.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(view_name="blueflow:asset-detail")
    tags_url = serializers.HyperlinkedIdentityField(view_name="blueflow:asset-tags")
    scans_url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:asset-scans"
    )
    external_links_url = serializers.HyperlinkedIdentityField(
        view_name="blueflow:asset-external-links"
    )

    asset_tags = AssetTagSerializer(read_only=True, many=True)
    asset_custom_fields = AssetCustomFieldSerializer(read_only=True, many=True)
    asset_vulnerabilities = MiniAssetVulnerabilitySerializer(read_only=True, many=True)

    display_name = serializers.CharField(
        max_length=126, allow_blank=True, allow_null=True, required=False
    )

    class Meta:
        """Wire this serializer to a model."""

        model = Asset

        # Fields defined in the schema
        asset_fields = tuple(f.name for f in model._meta.fields)  # noqa: SLF001

        # Fields that are computed (not stored directly in schema)
        computed_fields = (
            "url",
            "tags_url",
            "scans_url",
            "external_links_url",
            "display_name",
            "last_updated",
            "asset_tags",
            "asset_custom_fields",
            "asset_vulnerabilities",
        )

        fields = asset_fields + computed_fields

        read_only_fields: ClassVar = ["nic_vendor"]

    def validate_ip_address(self, ip_string: str) -> str | None:
        """If the IP address is empty, we coerce it to None.

        This happens anyway, when it gets stored in the database --
        doing it early avoids some problems with finding the asset in
        history.
        """
        if ip_string == "":
            return None
        return ip_string

    def validate_mac_address(self, mac_string: str) -> str | None:
        """If the MAC address is empty, we coerce it to None.

        This happens anyway, when it gets stored in the database --
        doing it early avoids some problems with finding the asset in
        history.

        This may not be necessary anymore
        """
        if mac_string == "":
            logger.debug("Coercing empty string MAC to None (was %r)", mac_string)
            return None
        return mac_string

    def validate_open_ports_tcp(self, ports_list: list) -> list:
        """Ensure that TCP ports are in the correct range.

        NOTE: For UDP, '0' is in fact an acceptable port... but not for TCP.
        """
        # Built-in field validator has already validated that we have a
        # list of integers - now we validate that they are in range.
        # Ideally, this should have been solved with a CHECK CONSTRAINT
        # at the database level, then we wouldn't have needed a
        # validator here.
        max_port = 65535
        if not all(1 <= port <= max_port for port in ports_list):
            _msg = "TCP Ports must be in range 1--65535"
            raise serializers.ValidationError(_msg)
        return sorted(set(ports_list))


class HistoricalAssetSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes asset history."""

    history_user = serializers.HyperlinkedRelatedField(
        view_name="blueflow:user-detail",
        read_only=True,
    )

    class Meta:
        """Wire this serializer to a model."""

        model = Asset.history.model
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

        model = Asset.history.model
        changed_fields = AssetSerializer.Meta.asset_fields
        fields = changed_fields + HistoricalAssetSerializer.Meta.historical_fields


class AssetFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    date_range = django_filters.DateRangeFilter(field_name="date_added")
    datetime_range = django_filters.DateTimeFromToRangeFilter(field_name="date_added")
    network = django_filters.NumberFilter(method="filter_network")
    no_network = drf_filters.BooleanFilter(method="filter_no_network")
    unassessed = drf_filters.BooleanFilter(method="filter_unassessed")
    assessed_factor = drf_filters.NumberFilter(method="filter_assessed_factor")
    group = django_filters.NumberFilter(field_name="groups")
    tag = django_filters.NumberFilter(field_name="tags")
    vulnerability = django_filters.NumberFilter(field_name="vulnerabilities__id")
    active_vulnerability = django_filters.NumberFilter(
        method="filter_active_vulnerability"
    )
    pulse = django_filters.NumberFilter(method="filter_pulse")

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
    def filter_pulse(_queryset: QuerySet, _name: str, value: int) -> QuerySet:
        """Get assets pertinent to a specific Pulse feed item."""
        try:
            pulse = PulseFeedItem.objects.get(external_pulse_id=value)
        except PulseFeedItem.DoesNotExist:
            return Asset.objects.none()

        return pulse.asset_qset()

    @staticmethod
    def filter_active_vulnerability(
        queryset: QuerySet, name: str, value: int
    ) -> QuerySet:
        """Get assets with a vulnerability open."""
        if name != "active_vulnerability":
            _msg = f"Unexpected filter name: {name!r}"
            raise ValueError(_msg)
        return queryset.filter(
            asset_vulnerabilities__vulnerability=value,
            asset_vulnerabilities__date_remediated__isnull=True,
            asset_vulnerabilities__date_ignored__isnull=True,
        )

    @staticmethod
    def filter_unassessed(queryset: QuerySet, _name: str, _value: bool) -> QuerySet:  # noqa: FBT001
        """Get assets that lack AssetRiskFactors.

        Calling with value False is a silly double negative ("not unassessed").
        """
        # TODO: Implement unassessed  # noqa: TD002,TD003,FIX002
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
        # TODO: Implement assessed_factor  # noqa: TD002,TD003,FIX002
        _msg = "Assessed factor is not implemented"
        raise NotImplementedError(_msg)

    class Meta:
        """Wire this filter to a model."""

        model = Asset

        # The first lookup in each field will be used as the default by
        # autocomplete.py.  "icontains" is usually a good choice.
        #
        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields = {  # noqa: RUF012
            "hostname": ["icontains"],
            "nic_vendor": ["icontains"],
            "category": ["icontains", "exact"],
            # TODO: Add risk score filters  # noqa: TD002,TD003,FIX002
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
            "custom_fields__field_name": ["istartswith"],
            "asset_custom_fields__value_text": ["istartswith"],
            "asset_vulnerabilities__date_remediated": ["isnull"],
            "asset_vulnerabilities__date_ignored": ["isnull"],
            # TODO: Add asset_risk_factors filters  # noqa: TD002,TD003,FIX002
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
    WaffleSwitchMixin, ChangeReasonMixin, PaginateRelationsMixin, viewsets.ModelViewSet
):
    """API endpoint for an Asset (representing a networked device).

    read: Return the given asset.

    See additional methods:
    `/changelog`
    `/external_links`
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
    `/risk_per_manufacturer`
    `/riskiest`
    `/summary`
    `/upsert` — DEPRECATED: use PATCH /api/assets/<id>/ or /bulk_update/

    In addition, there are several filtering and search terms available.

    create: Create a new asset
    delete: Delete the given asset
    update: Modify the given asset
    partial_update: Modify the given asset
    """

    waffle_switch = "core"

    renderer_classes = (
        *api_settings.DEFAULT_RENDERER_CLASSES,
        drf_csv_renderers.PaginatedCSVRenderer,
    )

    # NOTE: Order of mixins/base class is important!  Mixins that override
    #   methods *must come first* in order to properly override.  This is
    #   counterintuitive... but it's the way it is.  (Assiduous use of
    #   inspect.getmro() reveals that this is indeed the case.)

    # A model does have objects...
    queryset = Asset.objects.all()
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
        # 'asset_vulnerabilities__vulnerability__synopsis',
        "hostname",
        "ip_address",
        "mac_address",
        "manufacturer",
        "model",
        "name",
        "nic_vendor",
        "os",
        "owner",
        "serial_number",
        "tag_number",
        "tags__name",
        # The following field would enable search on custom field *name*
        # 'custom_fields__field_name',
        "asset_custom_fields__value_text",
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
            "nic_vendor",
            "manufacturer",
            "model",
            "os",
            "app_sw_version",
            "serial_number",
            "tag_number",
            "category",
            "date_added",
            # TODO: Add risk score filters  # noqa: TD002,TD003,FIX002
            "udi",
        ]
        context = super().get_renderer_context()
        if "fields" in self.request.GET:
            context["header"] = self.request.GET["fields"].split(",")
        else:
            context["header"] = default_headers
        return context

    def _validate_open_ports(self, ports: Any) -> list[str]:
        """Convert TCP port string to list.
        Convert string of integers to a sorted list of unique integers.

        Separator(s) can be one of: space, comma, semicolon, pipe, or newline,
        including repetitions of these.

        Added bonus: if falsey, return empty list.
        """
        if not ports:
            return []
        if not isinstance(ports, str):
            return ports

        sep_re = re.compile(r"[ ,;|\n]+")
        ports_list = re.split(sep_re, ports)
        return ports_list

    @staticmethod
    def _validate_mac_address(mac: str | None) -> str | None:
        """Convert an empty string MAC address to None.

        This would happen at a later point, but doing it explicitly here
        avoids a database error due to "non-unique" MAC when there's an
        existing empty MAC address.
        """
        return mac or None

    def update(self, request: Request, *args: int, **kwargs: str) -> Response:
        """Override update in order to convert TCP port string to list.

        NOTE: We can't use a "serializer validator" for this, since the
        validator would kick a string out (it really wants a list.)
        """
        if "open_ports_tcp" in request.data:
            request.data["open_ports_tcp"] = self._validate_open_ports(
                request.data["open_ports_tcp"]
            )
        if "mac_address" in request.data:
            request.data["mac_address"] = self._validate_mac_address(
                request.data["mac_address"]
            )
        return super().update(request, *args, **kwargs)

    def create(self, request: Request, *args: int, **kwargs: str) -> Response:
        """Override create in order to convert TCP port string to list.

        NOTE: (see 'update' method)
        """
        if "open_ports_tcp" in request.data:
            request.data["open_ports_tcp"] = self._validate_open_ports(
                request.data["open_ports_tcp"]
            )
        if "mac_address" in request.data:
            request.data["mac_address"] = self._validate_mac_address(
                request.data["mac_address"]
            )
        return super().create(request, *args, **kwargs)

    ################################
    # Detail methods/actions

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

    @action(detail=True)
    def external_links(self, _request: Request, _pk: int) -> Response:
        """Return a dictionary of (systemname, url) external links."""
        _msg = "Connectors have been removed"
        raise NotImplementedError(_msg)

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
        for f in Asset._meta.get_fields():  # noqa: SLF001
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

        for f in AssetCustomFieldName.objects.all():
            name = f.field_name
            cfv = AssetCustomField.objects.filter(asset_id=pk, field=f).first()
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

    @action(detail=True)
    def networks(self, request: Request, _pk: int) -> Response:
        """Networks that this asset belongs to."""
        # FUTURE: Replace with /api/networks/?asset=<pk>

        qset = self.get_object().network_qset()
        return self.paginate_relations(request, qset, "NetworkSerializer")

    @action(detail=True)
    def scans(self, request: Request, _pk: int) -> Response:
        """Return scans of the asset."""
        # FUTURE: Replace with /api/scans/?asset=<pk>

        scan_qset = self.get_object().scan_qset()
        return self.paginate_relations(request, scan_qset, "ScanSerializer")

    @action(detail=True)
    def similar(self, request: Request, _pk: int) -> Response:
        """Similar assets."""
        exclude_self = True
        if request.query_params.get("exclude_self") in ("false", "0"):
            exclude_self = False

        # This stuff might not be necessary.  The DRF pagination system
        # might take care of it (since it's the same serializer etc.
        qset = self.get_object().similar_qset(exclude_self=exclude_self)
        # TODO: Add risk score ordering  # noqa: TD002,TD003,FIX002
        return self.paginate_relations(request, qset, "AssetSerializer")

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
                tag = Tag.objects.get(pk=tag_id)
            except d_ex.ObjectDoesNotExist as err:
                raise serializers.ValidationError(
                    {
                        "tag_id": [f"Tag does not exist: id={tag_id}"],
                    }
                ) from err
            asset_tag = AssetTag(asset=asset, tag=tag, provenance="API")
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
                asset_tag = AssetTag.objects.get(asset=asset, tag=tag)
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

    @action(detail=False)
    def risk_per_manufacturer(self, request: Request) -> Response:
        """Calculate risk per manufacturer.

        Sort into one bin per manufacturer, sum the risks in each bin,
        and return the `limit` first ones + `others`.

        Seems like this could be accomplished by something like

              SELECT manufacturer, count(manufacturer), sum(risk_score)
                FROM blueflow_asset
               WHERE manufacturer IS NOT null
            GROUP BY manufacturer
            ORDER BY sum(risk_score) DESC;

        This is basically what we're doing with the Django ORM code
        below.  I.e., it becomes

               SELECT "blueflow_asset"."manufacturer",
                      COUNT("blueflow_asset"."manufacturer") AS "count",
                      SUM("blueflow_asset"."risk_score") AS "risk_score"
                 FROM "blueflow_asset"
            WHERE NOT ("blueflow_asset"."manufacturer" IS NULL)
             GROUP BY "blueflow_asset"."manufacturer"
             ORDER BY "risk_score" DESC
        """
        # TODO: Implement risk per manufacturer  # noqa: TD002,TD003,FIX002
        _msg = "Risk per manufacturer is not implemented"
        raise NotImplementedError(_msg)

    @action(detail=False)
    def riskiest(self, request: Request) -> Response:
        """Produce a paginated list of the "riskiest" assets."""
        # TODO: Implement riskiest  # noqa: TD002,TD003,FIX002
        _msg = "Riskiest is not implemented"
        raise NotImplementedError(_msg)

    @action(detail=False)
    def summary(self, _request: Request) -> Response:
        """Return summary about an asset queryset."""
        # TODO: Implement summary  # noqa: TD002,TD003,FIX002
        _msg = "Summary is not implemented"
        raise NotImplementedError(_msg)

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
        validated: list[tuple[Asset, AssetSerializer]] = []
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

            # Apply the same field normalisations as create/update.
            if "open_ports_tcp" in item:
                item["open_ports_tcp"] = self._validate_open_ports(
                    item["open_ports_tcp"]
                )
            if "mac_address" in item:
                item["mac_address"] = self._validate_mac_address(item["mac_address"])
            try:
                asset = Asset.objects.get(pk=asset_id)
            except Asset.DoesNotExist:
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

    @action(detail=False, methods=["POST"])
    def upsert(self, request: Request) -> Response:
        """Update or create an Asset (DEPRECATED).

        .. deprecated::
            Use ``PATCH /api/assets/<id>/`` for single updates.
            ``PATCH /api/assets/bulk_update/`` supports batch partial-updates
            only — it does not provide create-or-update-by-identity semantics
            and is not a drop-in replacement for this endpoint.
            This endpoint will be removed in a future release.

        The input is a JSON blob containing any Asset field.  The output is a
        copy of the updated or created asset.  The status code is 201 upon
        creation, 200 on update.

        The name "upsert" is a portmanteau of "UPDATE" and "INSERT" and is
        borrowed from database management.
        """
        logger.warning(
            "POST /api/assets/upsert/ is deprecated and will be removed in a future "
            "release. Use PATCH /api/assets/<id>/ for single updates. "
            "Note: PATCH /api/assets/bulk_update/ is for batch partial-updates only "
            "and is not a drop-in replacement."
        )
        # Ignore API calls that lack a MAC address.  Otherwise, we'd create
        # duplicate assets with each call!  The reason is because MAC is the
        # only way we can uniquely identify an asset for *update*.
        if "mac_address" not in request.data:
            return Response(
                {"detail": "Ignoring request without mac_address field."},
                status.HTTP_412_PRECONDITION_FAILED,
            )

        # Ignore ipv6_address and connect_port_tcp fields
        request.data.pop("ipv6_address", None)
        request.data.pop("connect_port_tcp", None)

        # Coerce ipv4_address to ip_address, override if appropriate
        ipv4_address = request.data.pop("ipv4_address", None)
        if ipv4_address is not None:
            request.data["ip_address"] = ipv4_address

        # Coerce identifier to name, override if appropriate
        identifier = request.data.pop("identifier", None)
        if identifier is not None:
            request.data["name"] = identifier

        # Grab last_seen, client_id, and provenance for
        # history_change_reason, with reasonable defaults
        last_seen = request.data.pop("last_seen", None)
        if not last_seen:
            last_seen = timezone.now()
        client_id = request.data.pop("client_id", None)
        if not client_id:
            client_id = "observer"
        provenance = request.data.pop("provenance", None)
        if not provenance:
            provenance = "Data"

        # Add "open_port_tcp" field to list of open tcp ports.  We'll save it,
        # then append it after the Asset is created or updated.  This avoids
        # clobbering an existing list of open ports in the case of updating an
        # existing asset.
        open_port_tcp = request.data.pop("open_port_tcp", None)

        # Update or create asset using custom logic for matching against
        # existing assets.  In this context, only mac_address will be used
        # for the match.
        asset, created = Asset.objects.update_or_create_by_priority(
            **request.data,
            defaults=request.data,
        )
        # Ported from experimental/testbed-build:bf_opencore/views/asset.py.
        # update_change_reason can fail when its filter returns None (e.g.
        # with netfields/ArrayField); fall back to updating the latest record.
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

        # Add port to list of open ports
        if open_port_tcp:
            updated = asset.open_ports_tcp_add(open_port_tcp)
            if updated:
                asset.save()

        # Serialize the created or updated asset object and return it in the
        # response.
        serializer = AssetSerializer(asset, context={"request": request})
        response = Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
        response["Deprecation"] = "true"
        response["Link"] = '</api/assets/{id}/>; rel="successor-version"'
        return response
