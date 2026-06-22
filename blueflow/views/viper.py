"""Views for the Viper integration.

Currently we provide a webhook registration endpoint that allows Viper to
query for a list of assets

The "real" response is handled by a Celery task.
"""

import typing

import drf_spectacular.utils as drf_spectacular
from rest_framework import (
    decorators,
    parsers,
    permissions,
    request,
    response,
    serializers,
    status,
    viewsets,
)

from blueflow import models
from blueflow.celery import tasks


class ViperWebhookSerializer(serializers.Serializer):
    """Serializer for the Viper webhook."""

    callback = serializers.CharField()
    since = serializers.DateTimeField()
    before = serializers.DateTimeField(required=False, default=None)
    max_pages = serializers.IntegerField()
    page_size = serializers.IntegerField()


class ViperWebhookResponseSerilizer(serializers.Serializer):
    request_id = serializers.CharField()


class ViperViewSet(viewsets.ViewSet):
    """ViewSet for the Viper integration."""

    permission_classes: typing.ClassVar = [permissions.AllowAny]
    parser_classes: typing.ClassVar = [parsers.JSONParser]
    serializer_class: typing.ClassVar = ViperWebhookSerializer

    @drf_spectacular.extend_schema(
        request=ViperWebhookSerializer,
        responses={
            202: ViperWebhookResponseSerilizer,
            400: drf_spectacular.OpenApiResponse(
                description="Validation error — malformed or incomplete webhook payload"
            ),
        },
        description="Register the viper callback endpoint for asset syncing",
    )
    @decorators.action(detail=False, methods=["post"])
    def webhook(self, request: request.Request) -> response.Response:
        """Register a viper webhook."""
        serializer = self.serializer_class(data=request.data)
        _ = serializer.is_valid(raise_exception=True)
        viper_data = models.ViperWebhookRequest(**serializer.validated_data)
        job = models.ViperWebhookJob.objects.create(
            callback=viper_data.callback,
            since=viper_data.since,
            before=viper_data.before,
            request_body=request.data,
        )
        tasks.viper_webhook.delay(viper_data.to_dict(), str(job.id))
        return response.Response(
            {"request_id": str(job.id)}, status=status.HTTP_202_ACCEPTED
        )
