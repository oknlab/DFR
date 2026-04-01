"""Django/DRF adapter stubs for OpenAPI extraction."""

from __future__ import annotations

from typing import Any


def serializer_to_schema(serializer_class: type[Any]) -> dict[str, Any]:
    """Best-effort DRF serializer introspection stub."""
    fields = getattr(serializer_class, "declared_fields", {})
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in fields},
    }


__all__ = ["serializer_to_schema"]
