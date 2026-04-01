"""OpenAPI schema helpers."""

from __future__ import annotations

from typing import Any


class DFRSchemaGenerator:
    """Very small OpenAPI 3.1 schema scaffold generator."""

    def generate(self, *, title: str, version: str, paths: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {"title": title, "version": version},
            "paths": paths or {},
        }


class DFRSampleGenerator:
    """Produces sample payloads for primitive schema properties."""

    def sample_for_type(self, typ: str) -> Any:
        return {
            "string": "example",
            "integer": 1,
            "number": 1.0,
            "boolean": True,
            "array": [],
            "object": {},
        }.get(typ, None)


__all__ = ["DFRSampleGenerator", "DFRSchemaGenerator"]
