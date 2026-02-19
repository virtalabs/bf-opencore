"""Join table for assets and vulns."""

import django_filters
from rest_framework.exceptions import MethodNotAllowed
from rest_framework import viewsets, serializers
from rest_framework.fields import IntegerField
from rest_framework.generics import get_object_or_404, Http404
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.bf_opencore.models import AssetGroup
from .group import GroupSerializer
from .utils import HugeLimitOffsetPagination


class AssetGroupSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes AssetGroup objects."""

    # Few public methods; that's just how serializers work

    url = serializers.HyperlinkedIdentityField(
        view_name="bf_opencore:assetgroup-detail")
    group = GroupSerializer(read_only=True)
    asset_id = IntegerField()
    group_id = IntegerField()

    class Meta:  # noqa
        model = AssetGroup
        fields = (
            'id',
            'asset_id',
            'group_id',
            'date_added',
            'provenance',

            # Fields that are created (not stored directly in schema)
            'group',
            'url',
        )


class AssetGroupFilter(django_filters.rest_framework.FilterSet):
    """FilterSet."""

    # Few public methods; that's just how django-filters work

    class Meta:  # noqa
        model = AssetGroup

        # Documentation about lookups is here:
        # https://docs.djangoproject.com/en/1.11/ref/models/querysets/#field-lookups
        fields = {
            'asset': ['exact'],
            'group': ['exact'],
            }


class AssetGroupViewSet(WaffleSwitchMixin, viewsets.ModelViewSet):
    """An AssetGroup links a group to an asset."""

    waffle_switch = "core"

    # AssetGroup model does have 'objects'
    queryset = AssetGroup.objects.all()
    serializer_class = AssetGroupSerializer
    filterset_class = AssetGroupFilter
    pagination_class = HugeLimitOffsetPagination

    def delete(self, request, *args, **kwargs):
        """Allow deletion with query args asset and group."""
        return self.destroy(request, *args, **kwargs)

    def get_object(self):
        """Allow get_object with asset / group combo.

        Regular get_object() expects a 'pk' kwarg.  We have another way,
        and thus need to override.
        """
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        if lookup_url_kwarg in self.kwargs:
            # This is how get_object() usually works (lookup_url_kwarg is 'pk')
            filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
            obj = get_object_or_404(queryset, **filter_kwargs)
        else:
            # We don't have 'pk'
            # Ensure we have one and only one AssetGroup, retrieved by
            # asset / group combo
            if self.request.method != 'DELETE':
                raise MethodNotAllowed(self.request.method)
            if not (('asset' in self.request.query_params) and
                    ('group' in self.request.query_params)):
                msg = ("To DELETE one AssetGroup, specify both 'asset' and "
                       "'group'.")
                raise MethodNotAllowed('DELETE', detail=msg)
            assert queryset.count() <= 1, (
                "Should only be possible to get 0 or 1 assetgroups here")
            if queryset.count() < 1:
                raise Http404("No AssetGroup matches the given query")
            obj = queryset.first()

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)

        return obj
