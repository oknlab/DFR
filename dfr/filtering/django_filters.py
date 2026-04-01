"""Simple filtering bridge helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def apply_filters(items: Iterable[Any], **criteria: Any) -> list[Any]:
    """Filter objects by direct attribute equality."""
    result = []
    for item in items:
        ok = True
        for key, expected in criteria.items():
            if getattr(item, key, object()) != expected:
                ok = False
                break
        if ok:
            result.append(item)
    return result


__all__ = ["apply_filters"]
