"""Pagination dependencies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PageParams:
    page: int = 1
    page_size: int = 20


def pagination_params(page: int = 1, page_size: int = 20) -> PageParams:
    """Normalize page params for downstream pagination handlers."""
    return PageParams(page=max(page, 1), page_size=max(page_size, 1))


__all__ = ["PageParams", "pagination_params"]
