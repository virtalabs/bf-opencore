"""Utilities for our views."""

import importlib
import logging

from rest_framework.pagination import LimitOffsetPagination

# Not using this decorator here but keeping it to help our clients
from rest_framework.response import Response
from simple_history import utils as hist_utils

logger = logging.getLogger(__name__)


def request_debug(fn):
    """Decorate view *functions*.

    In order to decorate viewset methods, must wrap this in
    'method_decorator' (which takes special care with the 'self'
    argument.)

        # For debugging
        from .utils import method_decorator, request_debug

        @method_decorator(request_debug, 'create')
        class MyViewSet(viewsets.ModelViewSet):
            # Class whose 'create' method is decorated.  You can
            # also specify any of the other API methods ('retrieve',
            # 'list', 'create', 'update', 'partial_update', 'destroy'),
            # or 'dispatch' which wraps all of them.
    """

    def wrapper(request, *args, **kwargs):
        # Docstring: see request_debug
        version = getattr(request, "version", None)
        try:
            query_params = request.query_params
            data = request.data
        except AttributeError:
            query_params = f"GET:{request.GET}"
            data = f"POST:{request.POST}"
        logger.debug(
            "request='%s'(m:%s,v:%s), args='%s', kwargs='%s'",
            request,
            request.method,
            version,
            args,
            kwargs,
        )
        # logger.debug("request headers: %s", pprint.pformat(request.META))
        logger.debug("request raw query: %s", request.META.get("QUERY_STRING"))
        # NOTE:
        #   request.query_params is basically the same as request.GET
        #   request.data is basically the same as request.POST
        logger.debug("request query_params: %s", query_params)
        logger.debug("request data: %s", data)
        # import pdb ; pdb.set_trace()
        return fn(request, *args, **kwargs)

    return wrapper


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
