"""Views for the Viper integration.

Currently we provide a webhook registration endpoint that allows Viper to
query for a list of assets
"""

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from bf_opencore.celery import celery_app, ViperWebhookRequest


class ViperViewSet(viewsets.ViewSet):
    """ViewSet for the Viper integration."""

    # TODO review authentication
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def webhook(self, request: Request) -> Response:
        """Registers a viper webhook."""
        viper_data = ViperWebhookRequest(**request.data)
        celery_app.send_task('viper.webhook', args=[viper_data])
        return Response(status=status.HTTP_202_ACCEPTED)