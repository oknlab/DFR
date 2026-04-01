"""FastAPI compatibility helpers for pagination params."""

from __future__ import annotations

from typing import Any

from dfr.pagination.core import PageNumberPagination


def paginate_from_query(items: list[Any], *, page: int = 1, page_size: int = 20):
    """Paginate a list using query-like page parameters."""
    return PageNumberPagination().paginate(items, page=page, page_size=page_size)


__all__ = ["paginate_from_query"]
