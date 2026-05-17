"""Pagination helpers with standard success envelope."""

from __future__ import annotations

from rest_framework import pagination

from .api_response import success_response


class ApplicationPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100

    def get_paginated_envelope(self, data, *, message: str = "OK"):
        return {
            "items": data,
            "pagination": {
                "page": self.page.number,
                "limit": self.page.paginator.per_page,
                "total_pages": self.page.paginator.num_pages,
                "total_items": self.page.paginator.count,
                "has_next": self.page.has_next(),
                "has_previous": self.page.has_previous(),
            },
        }

    def build_response(self, data, *, message: str = "OK", status_code: int = 200):
        return success_response(
            self.get_paginated_envelope(data),
            message=message,
            status_code=status_code,
        )
