"""Nested relation helper utilities."""

from __future__ import annotations

from typing import Any


def resolve_nested(instance: Any, name: str) -> Any:
    """Resolve a nested attribute with a helpful message."""
    if not hasattr(instance, name):
        raise AttributeError(f"Nested attribute {name!r} not present on {type(instance).__name__}.")
    return getattr(instance, name)


__all__ = ["resolve_nested"]
