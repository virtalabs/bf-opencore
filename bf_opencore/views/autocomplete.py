"""Search autocomplete for multiple database tables and fields.

Example:
$ curl localhost:8000/api/autocomplete/?term=192 | python -m json.tool
{
    "results": [
        {
            "term": "192",
            "suggestion": "Ea192M-Bk",
            "details": "Ea192M-Bk (model)",
            "url": "/search/?model__icontains=Ea192M-Bk"
        },
        {
            "term": "192",
            "suggestion": "192.168.5.249",
            "details": "192.168.5.249 (IP)",
            "url": "/search/?ip_address__istartswith=192.168.5.249"
        }
    ]
}
"""

import logging
import copy
import urllib.parse
import ipaddress
import netaddr

from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist, FieldError
from django.urls import reverse_lazy

from rest_framework import serializers, viewsets, permissions, status
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response

from bf_opencore.models import \
    Asset, Tag, SavedSearch, Vulnerability, Group, Network, AssetCustomField
from bf_opencore.views.asset import AssetFilter, AssetViewSet


logger = logging.getLogger(__name__)

# How many autocomplete entries of each type to return
AUTOCOMPLETE_LIMIT = 3


class Autocomplete():
    """Represent one Autocomplete object."""

    def __init__(self, term, suggestion, suggestion_type, query_dict,
                 base_url=None, append_query_params=True):
        """Copy inputs to member variables."""
        if base_url is None:
            base_url = reverse_lazy('bf_opencore:asset-list')
        self.term = term
        self.suggestion = suggestion
        self.suggestion_type = \
            Autocomplete.normalize_suggestion_type(suggestion_type)
        self.url = base_url
        if append_query_params:
            self.url += "?" + urllib.parse.urlencode(query_dict)
        self.query = query_dict

    @staticmethod
    def normalize_suggestion_type(orig_type):
        """Make a string for 'suggestion type' human readable."""
        # special cases
        if orig_type is None:
            return None
        if orig_type == 'os':
            return 'OS'

        # otherwise: replace underscores and use title caps
        ret = orig_type.replace('_', ' ')
        ret = ret.title()

        return ret


class AutocompleteSerializer(serializers.Serializer):
    """
    A serializer for Autocomplete search suggestions.

    Ref http://www.django-rest-framework.org/api-guide/serializers/
    """

    term = serializers.CharField()
    suggestion = serializers.CharField()
    suggestion_type = serializers.CharField()
    url = serializers.URLField()
    query = serializers.SerializerMethodField(read_only=True)

    @staticmethod
    def get_query(obj):
        """Get the raw query dictionary suitable for passing to AssetTable.

        Specifically patches up EUI objects that DRF cannot serialize.
        """
        q = dict(obj.query)
        for k, v in q.items():
            if isinstance(v, (netaddr.EUI, ipaddress.IPv4Address)):
                q[k] = str(v)
        return q


class AutocompleteViewSet(viewsets.ReadOnlyModelViewSet):
    """Lists search suggestions based on user entry."""

    serializer_class = AutocompleteSerializer
    # NOTE: Since this ViewSet doesn't have a proper queryset/associated
    #   model, it's not possible to check for permissions the
    #   automatic/Django way -- even checking the permissions causes an
    #   error.  We solve this by removing the standard
    #   DjangoModelPermissions class and sticking with the simple
    #   IsAuthenticated class.
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        """Return Autocomplete objects that match request."""
        # Parse query URL

        # HACK
        if "ordering" in self.request.query_params:
            # """"Temporary"""" hack - disable ordering, return empty queryset
            return Asset.objects.none()

        if "autocomplete" not in self.request.query_params:
            return []

        base_query_params = {str(k): str(v) for k, v in
                             self.request.query_params.items()}

        # remove some query params so they don't find their way to Asset
        # queries
        base_query_params.pop('offset', None)
        base_query_params.pop('limit', None)

        # the actual search term
        term = base_query_params.pop('autocomplete').strip()

        # Blank autocomplete requests return no results
        results = []
        if not term:
            return results

        # Special handling for /?search=STRING.
        # This is used when we want to "refine search" on a search page.
        #
        # DRF implements a case-insensitive search over several columns.
        # Django's ORM does not have an equivalent.  We will build a
        # disjunction of filters to mimic the DRF functionality.
        base_query = Q()  # 'null' query; other Q()s can be |-ed or &-ed to it
        if "search" in base_query_params:
            search_term = base_query_params["search"]
            base_query |= drf_search_term_to_django_orm_query(search_term)

        # Add the other query params to the query in a conjuction
        for django_filter, value in base_query_params.items():
            # Skip "search" since we already handled it
            if django_filter == "search":
                continue
            # Add a query
            base_query &= Q(**{django_filter: value})

        # Original value in any field
        query_dict = dict(base_query_params)  # copy
        query_dict["search"] = term           # modify copy
        results.append(Autocomplete(
            term=term,
            suggestion=term,
            suggestion_type=None,
            query_dict=query_dict,
        ))

        # Tag autocompletion
        results.extend(autocomplete_tag(
            term=term,
            base_query=base_query,
            base_query_params=base_query_params,
        ))

        results.extend(autocomplete_group(term))
        results.extend(autocomplete_network(term))
        results.extend(autocomplete_cidr(term, base_query_params))
        results.extend(autocomplete_vulnerability(term))
        results.extend(autocomplete_saved_search(term))
        results.extend(autocomplete_custom_fields(term))

        # Column-specific completions for each column specified in
        # asset.py.  Examples of columns incldue "model" and "ip_address".
        # We'll use the first lookup in the list made available by the
        # REST API.  Examples of lookups in include "gte" and "icontains".
        fields = AssetFilter.Meta.fields
        for column, lookups in fields.items():
            # skip some columns
            if column == 'id' or column.startswith('risk_score'):
                continue
            lookup = lookups[0]  # first lookup is the default
            results.extend(autocomplete_column(
                term=term,
                column=column,
                lookup=lookup,
                base_query=base_query,
                base_query_params=base_query_params,
            ))
        return results


def autocomplete_column(term, column, lookup, base_query,
                        base_query_params, limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects that search one Asset column."""
    # Get out if this isn't a column name.  We can tell if there's a double
    # underscore, which indicates a foreign key lookup.  For example,
    # tags__name.
    if "__" in column:
        return []

    # Build a Django ORM compatible filter string, e.g., model__icontains
    # Include any additional query params sent by the user
    orm_filter = "{}__{}".format(column, lookup)

    # Add filter to the query
    query = copy.deepcopy(base_query)  # copy
    query &= Q(**{orm_filter: term})   # modify

    # Grab a few assets from the column
    try:
        assets = Asset.objects.filter(query).distinct(column)[:limit]
    except ObjectDoesNotExist:
        assets = []

    # We're going to build a list of Autocomplete objects
    results = []

    # Add the original term string to the column-specific search
    if assets:
        query_dict = dict(base_query_params)
        query_dict[orm_filter] = term
        raw_column_autocomplete = Autocomplete(
            term=term,
            suggestion=term,
            suggestion_type=column,
            query_dict=query_dict,
        )
        results.append(raw_column_autocomplete)

    # Add specific assets to the column-specific search
    for asset in assets:
        suggestion = getattr(asset, column)  # Equivalent to "asset.model"
        query_dict = dict(base_query_params)
        if column == 'manufacturer':
            base_url = reverse_lazy('bf_opencore:asset-list')
            query_dict['manufacturer'] = suggestion
        elif column == 'model':
            base_url = reverse_lazy('bf_opencore:asset-list')
            query_dict['manufacturer'] = asset.manufacturer
            query_dict['model'] = suggestion
            suggestion = '{} {}'.format(asset.manufacturer, suggestion)
        else:
            # Other columns will just use the '/search/' page (the default)
            base_url = None
            query_dict[orm_filter] = suggestion
        results.append(Autocomplete(
            term=term,
            suggestion=suggestion,
            suggestion_type=column,
            query_dict=query_dict,
            base_url=base_url,
        ))

        # Avoid duplicate autocompletes.  Yes, we're removing the
        # item from the middle of the list.  This is just fine!
        if str(suggestion).lower() == term.lower():
            try:
                results.remove(raw_column_autocomplete)
            except ValueError:  # not in list, but that's our goal anyhow
                pass

    return results


def autocomplete_cidr(term, base_query_params, limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects for CIDRs.

    This is a super-ugly hack involving BOTH the built-in Python3 ipaddress
    library AND the 3rd party netaddr library.

    First, we use netaddr to parse a partially complete IP address, e.g.,
    "192.168" -> "192.168.0.0".  Unlike ipaddress, netaddr is very forgiving.
    To be clear, if we used ipaddress to parse "192.168" it would throw an
    error.  Thus, we use netaddr.

    Second, we use ipaddress to create an ip_network.  Unlike netaddr,
    ipaddress is very picky.  It won't allow things like "192.168.0.1/16".
    We're going to use that to our advantage.
    """
    # Parse complete, clean IP address string from partially complete IP
    # address string input, e.g., "192.168" -> "192.168.0.0".  netaddr is
    # tolerant of partially complete IP address strings, ipaddress is not.
    #
    # We allow a trailing '.', i.e., "192.168." is eqiuivalent to "192.168"

    try:
        cleaned_ip_str = str(netaddr.IPNetwork(term.rstrip('.')).ip)
    except netaddr.core.AddrFormatError:
        return []

    # Build CIDR from clean IP address string, e.g., "192.168.0.0" ->
    # "192.168.0.0/16".  netaddr will accept all bit masks, e.g.,
    # "192.168.0.0/8", while ipaddress will accept bit masks covering only
    # those bits containing zeros, e.g., "192.168.0.0/24" or "192.168.0.0/16"
    # We want the more restrictive behavaior, so we use ipaddress.
    nets = []
    for net_mask_bits in [8, 16, 24]:
        try:
            nets.append(str(ipaddress.ip_network('{}/{}'.format(
                cleaned_ip_str, net_mask_bits))))
        except ValueError:
            pass

    # Return a suggestion for each possible net
    results = []
    for net in nets:
        query_dict = dict(base_query_params)                         # copy
        query_dict["ip_address__net_contained_or_equal"] = str(net)  # modify
        autocomplete = Autocomplete(
            term=term,
            suggestion=str(net),
            suggestion_type='CIDR',
            query_dict=query_dict
        )
        results.append(autocomplete)

    return results[:limit]


def autocomplete_tag(term, base_query, base_query_params,
                     limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects for Tags."""
    # If there are no base query params, that means this is a fresh search.  We
    # can optimize for speed.  Any asset may be included, thus, all tags that
    # match the term string can be included.
    #
    # If there are base query params, that means we are refining a search, so
    # we only want to select tags that are associated with those assets that
    # match the previous search.  Again, the previous search is defined by
    # the base_query_params.
    if not base_query:
        # If we're doing a fresh search, then we can simply look for the tags
        tags = Tag.objects.filter(name__istartswith=term)
    else:
        # If we're refining a search over assets, we're only interested
        # in the tags belonging to the assets that currently match the
        # search/base_query.  This is a bit more complex and quite
        # inefficient.  It's not straightforward to obtain the relevant
        # Tags via SQL and espeically not via the Django ORM.  Thus we
        # resort to looping over the assets and collecting those tags.
        query = copy.deepcopy(base_query)         # copy
        query &= Q(tags__name__istartswith=term)  # modify
        assets = Asset.objects.filter(query)
        # THIS IS INEFFICIENT, but with Django's ORM there may not be a
        # better way.  We avoid searching EVERY asset by breaking after
        # finding `limit` unique tags.
        tags = set()
        for asset in assets:
            tags.update(asset.tags.all())
            if len(tags) >= limit:
                break
        tags = list(tags)

    # Build a list of autocomplete objects for each Tag
    results = []
    for tag in tags[:limit]:
        query_dict = dict(base_query_params)
        query_dict['tag'] = tag.id
        base_url = reverse_lazy('bf_opencore:tag-detail', args=[tag.id])
        autocomplete = Autocomplete(
            term=term,
            suggestion=tag.name,
            suggestion_type='Tag',
            query_dict=query_dict,
            base_url=base_url,
            append_query_params=False,
        )
        results.append(autocomplete)
    return results


def autocomplete_vulnerability(term, limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects for Vulnerabilities."""
    vulns = Vulnerability.objects.filter(synopsis__icontains=term)

    results = []
    for vuln in vulns[:limit]:
        base_url = reverse_lazy('bf_opencore:vulnerability-detail', args=[vuln.id])
        autocomplete = Autocomplete(
            term=term,
            suggestion=vuln.synopsis,
            suggestion_type='Vulnerability',
            query_dict={'vulnerability': vuln.id},
            base_url=base_url,
            append_query_params=False,
        )
        results.append(autocomplete)
    return results


def autocomplete_group(term, limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects for Groups."""
    groups = Group.objects.filter(name__istartswith=term)

    results = []
    for group in groups[:limit]:
        base_url = reverse_lazy('bf_opencore:group-detail', args=[group.id])
        autocomplete = Autocomplete(
            term=term,
            suggestion=group.name,
            suggestion_type='Group',
            base_url=base_url,
            query_dict={'group': group.id},
            append_query_params=False,
        )
        results.append(autocomplete)

    return results


def autocomplete_saved_search(term, limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects for saved searches."""
    searches = SavedSearch.objects.filter(name__istartswith=term)

    results = []
    for search in searches[:limit]:
        autocomplete = Autocomplete(
            term=term,
            suggestion=search.name,
            suggestion_type='Saved search',
            query_dict=search.search_query_dict,
        )
        results.append(autocomplete)

    return results


def autocomplete_network(term, limit=AUTOCOMPLETE_LIMIT):
    """Return list of Autocomplete objects for Networks."""
    networks = Network.objects.filter(name__istartswith=term)

    results = []
    for network in networks[:limit]:
        base_url = reverse_lazy('bf_opencore:network-detail', args=[network.id])
        autocomplete = Autocomplete(
            term=term,
            suggestion=network.name,
            suggestion_type='Network',
            base_url=base_url,
            query_dict={'network': network.id},
            append_query_params=False,
        )
        results.append(autocomplete)

    return results


def autocomplete_custom_fields(term, limit=3):
    """Return list of Autocomplete objects for custom fields."""
    custom_fields = AssetCustomField.objects.filter(
        value_text__istartswith=term).distinct('value_text')

    results = []
    if custom_fields.count() > 0:
        # Add the original term string to the field-specific search
        raw_column_autocomplete = Autocomplete(
            term=term,
            suggestion=term,
            suggestion_type='Custom Field',
            query_dict={'asset_custom_fields__value_text__istartswith': term},
            append_query_params=True,
        )
        results.append(raw_column_autocomplete)
    for custom_field in custom_fields[:limit]:
        suggestion = custom_field.value_text
        autocomplete = Autocomplete(
            term=term,
            suggestion=suggestion,
            suggestion_type='Custom Field',
            query_dict={'asset_custom_fields__value_text__istartswith':
                        custom_field.value_text},
            append_query_params=True,
        )
        results.append(autocomplete)
        # Avoid duplicate autocompletes.  Yes, we're removing the
        # item from the middle of the list.  This is just fine!
        if str(suggestion).lower() == term.lower():
            try:
                results.remove(raw_column_autocomplete)
            except ValueError:  # not in list, but that's our goal anyhow
                pass
    return results


def drf_search_term_to_django_orm_query(term):
    """Mimic DRF's /?search=STRING using a Django `OR` query on same fields.

    Helpful stack overflow post:
    https://stackoverflow.com/questions/26634874/how-can-i-make-django-search-in-multiple-fields-using-querysets-and-mysql-full

    Relevant Django documentation:
    https://docs.djangoproject.com/en/1.11/topics/db/queries/#complex-lookups-with-q-objects
    """
    # Our search fields match DRF's search fields
    search_fields = AssetViewSet.search_fields

    # Build a disjunction
    query = Q()
    for field in search_fields:
        query |= Q(**{f"{field}__icontains": term})
    return query


class AutocompleteAssetFieldViewSet(ViewSet):
    """Autocomplete a single Asset field."""

    # NOTE: Since this ViewSet doesn't have a proper queryset/associated
    #   model, it's not possible to check for permissions the
    #   automatic/Django way -- even checking the permissions causes an
    #   error.  We solve this by removing the standard
    #   DjangoModelPermissions class and sticking with the simple
    #   IsAuthenticated class.
    permission_classes = (permissions.IsAuthenticated,)

    @staticmethod
    def list(request, *args, **kwargs):
        """Get all distinct values for a single Asset field."""
        params = request.GET.copy()

        # name of an Asset field to fetch all values of
        field = params.pop('field', None)
        if field is None:
            return Response([], status=status.HTTP_400_BAD_REQUEST)

        # QueryDict.pop() returns a list; we just want one item
        field = field[0]

        # what's left in request parameters: constraints.  for example, if
        # field is 'model', we'll be fetching all the distinct values for
        # Asset.model, but in fact we want to fetch all the distinct values for
        # Asset.model where Asset.manufacturer has a certain value.
        constraints = params.dict()

        isnull_p = '{}__isnull'.format(field)
        try:
            vals = (Asset.objects.values(field)
                    .distinct()
                    .exclude(**{isnull_p: True})
                    .order_by(field))
            if constraints:
                vals = vals.filter(**constraints)
            return Response([str(val[field]) for val in vals])
        except FieldError:
            # raised for a bad field name or constraint field name
            return Response([], status=status.HTTP_400_BAD_REQUEST)
