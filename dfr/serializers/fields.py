"""Serializer field metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldInfo:
    max_length: int | None = None
    default: str | None = None


def django_char_field(*, max_length: int, default: str | None = None) -> FieldInfo:
    """Return lightweight field metadata for CharField-like definitions."""
    return FieldInfo(max_length=max_length, default=default)


__all__ = ["FieldInfo", "django_char_field"]
