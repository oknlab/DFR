"""ASGI dispatcher over DFR route registry."""

from __future__ import annotations

import inspect
import json
from typing import Any

from dfr.async_ import sync_to_async
from dfr.routing.registry import RouteRegistry
from dfr.types import Receive, Scope, Send


class UnifiedDispatcher:
    """Dispatch requests to sync or async handlers from a single registry."""

    def __init__(self, registry: RouteRegistry) -> None:
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._send_plain(send, 500, "Unsupported scope type")
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()

        for route in self.registry:
            if route.path == path and method in route.methods:
                result = await self._invoke(route.endpoint, scope)
                await self._send_json(send, 200, result)
                return

        await self._send_plain(send, 404, "Not Found")

    async def _invoke(self, endpoint: Any, scope: Scope) -> Any:
        if inspect.iscoroutinefunction(endpoint):
            return await endpoint(scope)
        return await sync_to_async(endpoint, scope)

    async def _send_json(self, send: Send, status_code: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        await send({"type": "http.response.start", "status": status_code, "headers": [[b"content-type", b"application/json"]]})
        await send({"type": "http.response.body", "body": body})

    async def _send_plain(self, send: Send, status_code: int, text: str) -> None:
        await send({"type": "http.response.start", "status": status_code, "headers": [[b"content-type", b"text/plain; charset=utf-8"]]})
        await send({"type": "http.response.body", "body": text.encode("utf-8")})


__all__ = ["UnifiedDispatcher"]
