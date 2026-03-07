"""Utilities for our views."""

import importlib
import logging

from rest_framework.pagination import LimitOffsetPagination

# Not using this decorator here but keeping it to help our clients
from rest_framework.response import Response
from simple_history import utils as hist_utils

logger = logging.getLogger(__name__)


class PaginateRelationsMixin:
    """Provides a method that paginates, and generates response."""

    def paginate_relations(self, request, qset, serializer_name):
        """Paginates, and serializes, the data from the queryset."""
        # Need to do the import at runtime in order to avoid problems
        # with cyclic import
        views = importlib.import_module("bf_opencore.views")
        serializer = getattr(views, serializer_name)

        page = self.paginate_queryset(qset)
        if page is not None:
            serializer = serializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        # No pagination; just return them all
        serializer = serializer(qset.all(), many=True, context={"request": request})
        return Response(serializer.data)


class HugeLimitOffsetPagination(LimitOffsetPagination):
    """Limit/offset pagination but with huge limit (1000000)."""

    default_limit = 1000000


class ChangeReasonMixin:
    """Mixins that provide a change reason.

    Useful for models that have a history via django-simple-history.
    """

    def _update_change_reason(self, instance, default_reason):
        change_reason = self.request.data.get("change_reason", default_reason)
        hist_utils.update_change_reason(instance, change_reason)

    def perform_update(self, serializer):
        """Add an update_change_reason hook for 'update' (PUT)."""
        instance = serializer.save()
        self._update_change_reason(instance, "PUT/PATCH API")

    def perform_create(self, serializer):
        """Add an update_change_reason hook for 'create' (POST)."""
        instance = serializer.save()
        self._update_change_reason(instance, "POST API")

    def perform_destroy(self, instance):
        """Add an update_change_reason hook for 'destroy' (DELETE)."""
        instance.delete()
        self._update_change_reason(instance, "DELETE API")
