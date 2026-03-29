"""Public package exports for DFR.

This module uses lazy attribute loading so lightweight modules (e.g. `dfr.sync`)
can be imported in environments where optional dependencies are unavailable.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "CurrentUser",
    "DFRApp",
    "Depends",
    "ModelSchema",
    "generate_openapi",
    "include_django_urls",
    "include_router",
    "route",
]

__version__ = "0.1.0"

_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "DFRApp": ("dfr.app", "DFRApp"),
    "route": ("dfr.routing", "route"),
    "include_router": ("dfr.routing", "include_router"),
    "include_django_urls": ("dfr.routing", "include_django_urls"),
    "ModelSchema": ("dfr.serializers", "ModelSchema"),
    "Depends": ("dfr.deps", "Depends"),
    "CurrentUser": ("dfr.auth", "CurrentUser"),
    "generate_openapi": ("dfr.openapi", "generate_openapi"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module 'dfr' has no attribute '{name}'")
    module_name, symbol = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, symbol)
    globals()[name] = value
    return value
