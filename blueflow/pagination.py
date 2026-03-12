"""Pagination classes for blueflow API."""

from rest_framework.pagination import LimitOffsetPagination


class HugeLimitOffsetPagination(LimitOffsetPagination):
    """Limit/offset pagination but with huge limit (1000000)."""

    default_limit = 1000000
