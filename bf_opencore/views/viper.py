"""Views for the Viper integration.

Currently we provide a webhook registration endpoint that allows Viper to
query for a list of assets

The "real" response is handled by a Celery task.
"""

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.parsers import JSONParser

from bf_opencore.celery import viper_webhook, ViperWebhookRequest



class ViperViewSet(viewsets.ViewSet):
    """ViewSet for the Viper integration."""

    # TODO review authentication
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @action(detail=False, methods=['post'])
    def webhook(self, request: Request) -> Response:
        """Registers a viper webhook."""
        viper_data = ViperWebhookRequest(**request.data)
        viper_webhook.delay(viper_data.to_dict())
        return Response(status=status.HTTP_202_ACCEPTED)