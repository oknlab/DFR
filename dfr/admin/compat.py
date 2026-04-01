"""Admin compatibility helpers."""

from __future__ import annotations

from typing import Any


def build_admin_registration(model: type[Any], admin_class: type[Any] | None = None) -> tuple[type[Any], type[Any] | None]:
    """Return a normalized registration tuple for deferred admin wiring."""
    return model, admin_class


__all__ = ["build_admin_registration"]
