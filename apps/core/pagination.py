"""Pagination classes for ff-consumer API."""

from rest_framework.pagination import CursorPagination as _CursorPagination
from rest_framework.response import Response


class CursorPagination(_CursorPagination):
    """Cursor-based pagination with a consistent response shape."""

    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = "-created_at"

    def get_paginated_response(self, data):
        return Response(
            {
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "count": None,
                "results": data,
            }
        )
