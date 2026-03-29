"""Pagination backends and response envelope helpers for DFR."""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import Any, Protocol

from django.db.models import QuerySet

from dfr.permissions import DFRRequestAdapter
from dfr.sync import run_sync

__all__ = [
    "AsyncPagination",
    "BasePagination",
    "CursorPagination",
    "LimitOffsetPagination",
    "PageNumberPagination",
    "PaginationError",
    "paginate",
    "paginate_async",
]


class PaginationError(RuntimeError):
    """Raised when pagination input is invalid."""


class BasePagination:
    """DRF-style pagination base class."""

    def paginate_queryset(self, queryset: QuerySet[Any], request: DFRRequestAdapter) -> list[Any]:
        raise NotImplementedError

    def get_paginated_response(self, data: list[Any]) -> dict[str, Any]:
        raise NotImplementedError


class AsyncPagination(Protocol):
    """Async-native pagination protocol."""

    async def paginate_queryset(self, queryset: QuerySet[Any], request: DFRRequestAdapter) -> list[Any]:
        ...

    def get_paginated_response(self, data: list[Any]) -> dict[str, Any]:
        ...


@dataclass(slots=True)
class LimitOffsetPagination(BasePagination):
    """Limit/offset pagination with next/previous envelopes."""

    default_limit: int = 20
    max_limit: int = 100
    count: int = 0
    limit: int = 20
    offset: int = 0

    def paginate_queryset(self, queryset: QuerySet[Any], request: DFRRequestAdapter) -> list[Any]:
        params = request.query_params
        limit = _to_int(params.get("limit"), self.default_limit)
        offset = _to_int(params.get("offset"), 0)
        if limit < 1:
            raise PaginationError("limit must be >= 1")
        limit = min(limit, self.max_limit)
        if offset < 0:
            raise PaginationError("offset must be >= 0")

        self.limit = limit
        self.offset = offset
        self.count = queryset.count()
        return list(queryset[offset : offset + limit])

    def get_paginated_response(self, data: list[Any]) -> dict[str, Any]:
        next_offset = self.offset + self.limit
        prev_offset = max(self.offset - self.limit, 0)
        next_link = f"?limit={self.limit}&offset={next_offset}" if next_offset < self.count else None
        prev_link = f"?limit={self.limit}&offset={prev_offset}" if self.offset > 0 else None
        return {
            "count": self.count,
            "next": next_link,
            "previous": prev_link,
            "results": data,
        }


@dataclass(slots=True)
class PageNumberPagination(BasePagination):
    """Page-number pagination with count and total pages."""

    page_size: int = 20
    max_page_size: int = 100
    count: int = 0
    page: int = 1
    total_pages: int = 0

    def paginate_queryset(self, queryset: QuerySet[Any], request: DFRRequestAdapter) -> list[Any]:
        params = request.query_params
        page = _to_int(params.get("page"), 1)
        page_size = _to_int(params.get("page_size"), self.page_size)
        if page < 1:
            raise PaginationError("page must be >= 1")
        if page_size < 1:
            raise PaginationError("page_size must be >= 1")

        self.page = page
        self.page_size = min(page_size, self.max_page_size)
        self.count = queryset.count()
        self.total_pages = math.ceil(self.count / self.page_size) if self.count else 0

        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return list(queryset[start:end])

    def get_paginated_response(self, data: list[Any]) -> dict[str, Any]:
        return {
            "count": self.count,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "results": data,
        }


@dataclass(slots=True)
class CursorPagination(BasePagination):
    """Cursor pagination using base64-encoded integer position."""

    page_size: int = 20
    ordering: str = "-id"
    cursor_query_param: str = "cursor"
    next_cursor: str | None = None
    previous_cursor: str | None = None

    def paginate_queryset(self, queryset: QuerySet[Any], request: DFRRequestAdapter) -> list[Any]:
        params = request.query_params
        raw_cursor = params.get(self.cursor_query_param)
        position = _decode_cursor(raw_cursor) if raw_cursor else 0

        ordering_expr = self.ordering
        ordered = queryset.order_by(ordering_expr)

        start = max(position, 0)
        end = start + self.page_size
        rows = list(ordered[start:end])

        if end < ordered.count():
            self.next_cursor = _encode_cursor(end)
        else:
            self.next_cursor = None

        prev = max(start - self.page_size, 0)
        self.previous_cursor = _encode_cursor(prev) if start > 0 else None
        return rows

    def get_paginated_response(self, data: list[Any]) -> dict[str, Any]:
        return {
            "next_cursor": self.next_cursor,
            "previous_cursor": self.previous_cursor,
            "results": data,
        }


def paginate(queryset: QuerySet[Any], request: Any, pagination_class: type[BasePagination] | BasePagination) -> dict[str, Any]:
    """Paginate queryset in sync flow and return response envelope."""

    adapter = DFRRequestAdapter(request)
    paginator = pagination_class() if isinstance(pagination_class, type) else pagination_class
    data = paginator.paginate_queryset(queryset, adapter)
    return paginator.get_paginated_response(data)


async def paginate_async(
    queryset: QuerySet[Any],
    request: Any,
    pagination_class: type[Any] | Any,
) -> dict[str, Any]:
    """Paginate queryset in async flow and return response envelope."""

    adapter = DFRRequestAdapter(request)
    paginator = pagination_class() if isinstance(pagination_class, type) else pagination_class

    if hasattr(paginator, "paginate_queryset") and _is_async_callable(paginator.paginate_queryset):
        data = await paginator.paginate_queryset(queryset, adapter)
    else:
        # FOOTGUN: queryset count/slicing are sync ORM operations; offload in async request flow.
        data = await run_sync(paginator.paginate_queryset, queryset, adapter, thread_sensitive=True)
    return paginator.get_paginated_response(data)


def _to_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _encode_cursor(position: int) -> str:
    return base64.urlsafe_b64encode(str(position).encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> int:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return int(decoded)
    except Exception as exc:
        raise PaginationError("Invalid cursor value. Ensure cursor is generated by this API.") from exc


def _is_async_callable(fn: Any) -> bool:
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    return bool(code.co_flags & 0x80)
