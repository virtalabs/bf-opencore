"""Views for the Viper integration.

Currently we provide a webhook registration endpoint that allows Viper to
query for a list of assets

The "real" response is handled by a Celery task.
"""

from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from bf_opencore.celery.tasks import viper_webhook
from bf_opencore.models.viper import ViperWebhookRequest


class ViperWebhookSerializer(serializers.Serializer):
    """Serializer for the Viper webhook."""

    callback = serializers.URLField()
    since = serializers.DateTimeField()
    before = serializers.DateTimeField(required=False, default=None)
    max_pages = serializers.IntegerField()
    page_size = serializers.IntegerField()


class ViperViewSet(viewsets.ViewSet):
    """ViewSet for the Viper integration."""

    # TODO review authentication
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    serializer_class = ViperWebhookSerializer

    @action(detail=False, methods=["post"])
    def webhook(self, request: Request) -> Response:
        """Registers a viper webhook."""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        viper_data = ViperWebhookRequest(**serializer.validated_data)
        viper_webhook.delay(viper_data.to_dict())
        return Response(status=status.HTTP_202_ACCEPTED)
