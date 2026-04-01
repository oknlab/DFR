"""OpenAPI schema helpers."""

from __future__ import annotations

from typing import Any


class DFRSchemaGenerator:
    """OpenAPI 3.1 schema scaffold generator with route introspection."""

    def generate(self, *, title: str, version: str, paths: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {"title": title, "version": version},
            "paths": paths or {},
        }

    def paths_from_registry(self, registry) -> dict[str, Any]:
        """Build OpenAPI `paths` from a DFR route registry."""
        result: dict[str, Any] = {}
        for route in registry:
            path_item = result.setdefault(route.path, {})
            for method in route.methods:
                path_item[method.lower()] = {
                    "summary": getattr(route.endpoint, "__name__", "handler"),
                    "responses": {"200": {"description": "Successful Response"}},
                }
        return result


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
