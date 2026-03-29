"""OpenAPI schema generation for DFR.

Example:
    from dfr.openapi import generate_openapi

    schema = generate_openapi(app)
"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_args, get_origin

from dfr.app import DFRApp, DFRBootstrapError
from dfr.routing import get_registry
from dfr.serializers import ModelSchema, _MODEL_TO_SCHEMA
from dfr.types import DFRBootPhase, RouteEntry

__all__ = ["generate_openapi"]

_PATH_PARAM_RE = re.compile(r"\{(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)(?::(?P<type>[a-zA-Z_][a-zA-Z0-9_]*))?\}")


def generate_openapi(app: DFRApp) -> dict[str, Any]:
    """Generate OpenAPI 3.1 schema for all registered DFR routes.

    Args:
        app: Bootstrapped DFR application.

    Returns:
        OpenAPI schema dictionary.

    Raises:
        DFRBootstrapError: If app is not in READY phase.
    """

    if app.boot_phase is not DFRBootPhase.READY:
        raise DFRBootstrapError(
            "OpenAPI generation requires a bootstrapped app. Call app.bootstrap() before generate_openapi()."
        )

    registry = get_registry()
    entries = registry.entries

    paths: dict[str, dict[str, Any]] = {}
    tags_seen: set[str] = set()
    components: dict[str, Any] = {"schemas": {}}

    for entry in entries:
        path_item = paths.setdefault(entry.path, {})
        for method in sorted(entry.methods):
            operation = _build_operation(entry, method)
            path_item[method.lower()] = operation
            for tag in operation.get("tags", []):
                tags_seen.add(tag)

            request_body = _build_request_body(entry, method)
            if request_body is not None:
                operation["requestBody"] = request_body

            responses = _build_responses(entry)
            operation["responses"] = responses

        _collect_components(components, entry)

    tags = [{"name": tag} for tag in sorted(tags_seen)]

    schema: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": app.settings.title,
            "version": app.settings.version,
        },
        "paths": paths,
        "components": {
            "schemas": components["schemas"],
            "securitySchemes": {
                "sessionAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "sessionid",
                },
                "tokenAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "Token",
                },
            },
        },
        "security": [{"sessionAuth": []}, {"tokenAuth": []}],
        "tags": tags,
    }
    return schema


def _build_operation(entry: RouteEntry, method: str) -> dict[str, Any]:
    operation_id = _operation_id(entry, method)
    parameters = _extract_path_parameters(entry.path)

    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": list(entry.tags),
        "parameters": parameters,
    }
    return operation


def _operation_id(entry: RouteEntry, method: str) -> str:
    if entry.name:
        return f"{method.lower()}_{entry.name}"
    qualname = getattr(entry.handler, "__qualname__", "handler")
    return f"{method.lower()}_{qualname.replace('.', '_')}"


def _extract_path_parameters(path: str) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    for match in _PATH_PARAM_RE.finditer(path):
        name = match.group("name")
        type_name = (match.group("type") or "str").lower()
        schema_type, schema_format = _openapi_scalar_for_path_type(type_name)

        schema: dict[str, Any] = {"type": schema_type}
        if schema_format is not None:
            schema["format"] = schema_format

        params.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": schema,
            }
        )
    return params


def _openapi_scalar_for_path_type(type_name: str) -> tuple[str, str | None]:
    mapping: dict[str, tuple[str, str | None]] = {
        "int": ("integer", "int32"),
        "str": ("string", None),
        "uuid": ("string", "uuid"),
        "slug": ("string", None),
        "path": ("string", None),
    }
    return mapping.get(type_name, ("string", None))


def _build_request_body(entry: RouteEntry, method: str) -> dict[str, Any] | None:
    if method.upper() not in {"POST", "PUT", "PATCH"}:
        return None

    schema = _infer_request_schema(entry.handler)
    if schema is None:
        return None

    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": schema,
            }
        },
    }


def _build_responses(entry: RouteEntry) -> dict[str, Any]:
    response_schema = _infer_response_schema(entry.handler)
    content: dict[str, Any] = {}
    if response_schema is not None:
        content = {
            "application/json": {
                "schema": response_schema,
            }
        }

    return {
        "200": {
            "description": "Successful response",
            "content": content,
        }
    }


def _infer_request_schema(handler: Any) -> dict[str, Any] | None:
    signature = inspect.signature(handler)
    for param in signature.parameters.values():
        if param.name == "request":
            continue
        if param.annotation is inspect._empty:
            continue
        schema = _schema_from_annotation(param.annotation)
        if schema is not None:
            return schema
    return None


def _infer_response_schema(handler: Any) -> dict[str, Any] | None:
    signature = inspect.signature(handler)
    annotation = signature.return_annotation
    if annotation is inspect._empty:
        return None
    return _schema_from_annotation(annotation)


def _schema_from_annotation(annotation: Any) -> dict[str, Any] | None:
    origin = get_origin(annotation)

    if origin is list:
        args = get_args(annotation)
        if not args:
            return {"type": "array", "items": {"type": "object"}}
        item_schema = _schema_from_annotation(args[0]) or {"type": "object"}
        return {"type": "array", "items": item_schema}

    if origin is dict:
        return {"type": "object"}

    if inspect.isclass(annotation) and issubclass(annotation, ModelSchema):
        return {"$ref": f"#/components/schemas/{annotation.__name__}"}

    if inspect.isclass(annotation):
        scalar_map: dict[type[Any], dict[str, Any]] = {
            str: {"type": "string"},
            int: {"type": "integer", "format": "int32"},
            float: {"type": "number", "format": "float"},
            bool: {"type": "boolean"},
        }
        return scalar_map.get(annotation, {"type": "object"})

    return None


def _collect_components(components: dict[str, Any], entry: RouteEntry) -> None:
    schemas: dict[str, Any] = components["schemas"]

    for schema_cls in _MODEL_TO_SCHEMA.values():
        name = schema_cls.__name__
        if name in schemas:
            continue
        schemas[name] = schema_cls.model_json_schema(ref_template="#/components/schemas/{model}")

    signature = inspect.signature(entry.handler)
    for param in signature.parameters.values():
        if param.annotation is inspect._empty:
            continue
        _collect_annotation_schema(schemas, param.annotation)

    if signature.return_annotation is not inspect._empty:
        _collect_annotation_schema(schemas, signature.return_annotation)


def _collect_annotation_schema(schemas: dict[str, Any], annotation: Any) -> None:
    origin = get_origin(annotation)
    if origin in {list, tuple, set}:
        for arg in get_args(annotation):
            _collect_annotation_schema(schemas, arg)
        return

    if inspect.isclass(annotation) and issubclass(annotation, ModelSchema):
        name = annotation.__name__
        if name not in schemas:
            schemas[name] = annotation.model_json_schema(ref_template="#/components/schemas/{model}")
