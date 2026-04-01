"""FastAPI router adapter utilities."""

from __future__ import annotations

from typing import Any


class FastAPIRouterAdapter:
    """Resolve endpoints from an attached FastAPI/Starlette router object."""

    def __init__(self) -> None:
        self._router: Any | None = None

    def attach_router(self, router: Any) -> None:
        self._router = router

    def resolve(self, path: str, method: str) -> tuple[Any, dict[str, Any]] | None:
        if self._router is None:
            return None

        routes = getattr(self._router, "routes", [])
        for route in routes:
            route_path = getattr(route, "path", None)
            methods = getattr(route, "methods", set())
            endpoint = getattr(route, "endpoint", None)
            if route_path == path and method in {m.upper() for m in methods}:
                return endpoint, {}
        return None


__all__ = ["FastAPIRouterAdapter"]
