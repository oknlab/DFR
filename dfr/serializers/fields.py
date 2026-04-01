"""Serializer field metadata helpers."""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass

_HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None

if _HAS_PYDANTIC:
    pydantic = importlib.import_module("pydantic")
    Field = pydantic.Field

    def django_char_field(*, max_length: int, default: str | None = None):
        """Return a Pydantic Field configured like Django CharField."""
        return Field(default=default, max_length=max_length)

else:

    @dataclass(frozen=True, slots=True)
    class FieldInfo:
        max_length: int | None = None
        default: str | None = None

    def django_char_field(*, max_length: int, default: str | None = None) -> FieldInfo:
        """Fallback field metadata when pydantic is unavailable."""
        return FieldInfo(max_length=max_length, default=default)


__all__ = ["django_char_field", "_HAS_PYDANTIC"]
