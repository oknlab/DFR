"""DFR application entry point."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dfr.conf import DFRConfig
from dfr.routing import RouteRegistry, UnifiedDispatcher
from dfr.types import Receive, Scope, Send


class DFR:
    """Main DFR ASGI application container."""

    def __init__(self, config: DFRConfig) -> None:
        self.config = config
        self.registry = RouteRegistry()
        self.dispatcher = UnifiedDispatcher(self.registry)

    def route(self, path: str, methods: list[str] | tuple[str, ...] = ("GET",)):
        """Register a route on this app instance."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.registry.add(path=path, methods=methods, endpoint=func)
            return func

        return decorator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.dispatcher(scope, receive, send)


__all__ = ["DFR"]
