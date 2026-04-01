"""Route registration primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dfr.exceptions import RoutingError


@dataclass(slots=True)
class Route:
    """Registered route metadata."""

    path: str
    methods: tuple[str, ...]
    endpoint: Callable[..., Any]
    dependencies: tuple[str, ...] = ()


class RouteRegistry:
    """Container for DFR routes."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(
        self,
        path: str,
        methods: list[str] | tuple[str, ...],
        endpoint: Callable[..., Any],
        dependencies: list[str] | tuple[str, ...] = (),
    ) -> Route:
        if not path.startswith("/"):
            raise RoutingError(f"Route path must start with '/'. Got: {path!r}")
        route = Route(
            path=path,
            methods=tuple(m.upper() for m in methods),
            endpoint=endpoint,
            dependencies=tuple(dependencies),
        )
        self._routes.append(route)
        return route

    def __iter__(self):
        return iter(self._routes)

    def __len__(self) -> int:
        return len(self._routes)


def route(
    path: str,
    methods: list[str] | tuple[str, ...] = ("GET",),
    *,
    registry: RouteRegistry | None = None,
    dependencies: list[str] | tuple[str, ...] = (),
):
    """Decorator that registers an endpoint in a route registry."""

    target_registry = registry if registry is not None else _default_registry

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        target_registry.add(path=path, methods=methods, endpoint=func, dependencies=dependencies)
        return func

    return decorator


def include(registry: RouteRegistry | None = None) -> RouteRegistry:
    """Return the provided registry or the global default."""
    return registry if registry is not None else _default_registry


_default_registry = RouteRegistry()

__all__ = ["Route", "RouteRegistry", "include", "route"]
