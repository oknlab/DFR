"""Pagination implementations."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, ceil(self.total / self.page_size))


class PageNumberPagination:
    """Classic page-number pagination strategy."""

    def paginate(self, data: Sequence[T], *, page: int = 1, page_size: int = 20) -> Page[T]:
        normalized_page = max(page, 1)
        normalized_size = max(page_size, 1)
        start = (normalized_page - 1) * normalized_size
        end = start + normalized_size
        items = list(data[start:end])
        return Page(items=items, page=normalized_page, page_size=normalized_size, total=len(data))


__all__ = ["Page", "PageNumberPagination"]
