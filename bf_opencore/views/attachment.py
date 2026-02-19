"""ViewSet for attachments."""

import logging

from rest_framework import viewsets, serializers
from waffle.mixins import WaffleSwitchMixin

from bf_opencore.models import Attachment

from .utils import HugeLimitOffsetPagination
from .utils import ChangeReasonMixin

# For debugging
from .utils import method_decorator, request_debug

logger = logging.getLogger(__name__)


class AttachmentSerializer(serializers.HyperlinkedModelSerializer):
    """Serializes attachments.

    Teaches the rest_framework (the ViewSet) which fields to expect.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="bf_opencore:attachment-detail")
    asset = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='bf_opencore:asset-detail'
        )
    asset_id = serializers.IntegerField(required=False)
    file_name = serializers.CharField(required=False)

    class Meta:  # noqa
        """Wire this serializer to a model."""

        model = Attachment
        fields = (
            'id',
            'display_name',
            'name',
            'file',
            'file_name',
            'asset',
            'asset_id',
            'manufacturer',
            'model',
            'size_bytes',
            'date_added',
            'added_by',

            # Fields that are created (not stored directly in schema)
            'url',
        )

    def validate(self, attrs):
        """Set original file name at upload."""
        logger.debug("Got raw data: %s", attrs)
        if 'file_name' not in attrs:
            attrs['file_name'] = attrs['file'].name
        return super().validate(attrs)

    def create(self, validated_data):
        """For debugging."""
        logger.debug("received validated data %s", validated_data)
        r = super().create(validated_data)
        logger.debug("created %s", r)
        return r


@method_decorator(request_debug, 'create')
class AttachmentViewSet(WaffleSwitchMixin, ChangeReasonMixin, viewsets.ModelViewSet):
    """Attachment associated with one or more assets."""

    waffle_switch = "core"

    # Attachment model does have 'objects'
    queryset = Attachment.objects.order_by('-date_added')
    serializer_class = AttachmentSerializer
    pagination_class = HugeLimitOffsetPagination
    filterset_fields = {
        'asset': ['exact'],
        'model': ['iexact', 'isnull'],
        'manufacturer': ['iexact', 'isnull'],
    }

    def create(self, request, *args, **kwargs):
        """For debugging."""
        logger.debug('creating')
        r = super().create(request, *args, **kwargs)
        logger.debug('created %s', r)
        return r
