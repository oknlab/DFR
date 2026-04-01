"""DRF filter backend compatibility adapter."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dfr.filtering.django_filters import apply_filters


class DRFFilterAdapter:
    """Expose simple filtering via DRF-like `filter_queryset` API."""

    def filter_queryset(self, request: Any, queryset: Iterable[Any], view: Any | None = None) -> list[Any]:
        params = getattr(request, "query_params", {})
        return apply_filters(queryset, **dict(params))


__all__ = ["DRFFilterAdapter"]
