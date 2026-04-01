"""Adapter utilities to run Django-like middleware in ASGI chains."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from dfr.async_ import sync_to_async
from dfr.types import Receive, Scope, Send

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class DjangoMiddlewareASGIAdapter:
    """Wrap middleware callable into ASGI-compatible chain.

    The wrapped middleware receives `(scope, call_next)` and may be sync or async.
    """

    def __init__(self, middleware: Callable[..., Any]) -> None:
        self.middleware = middleware

    def wrap(self, app: ASGIApp) -> ASGIApp:
        async def wrapped(scope: Scope, receive: Receive, send: Send) -> None:
            async def call_next() -> None:
                await app(scope, receive, send)

            result = self.middleware(scope, call_next)
            if hasattr(result, "__await__"):
                await result
            elif result is not None:
                await sync_to_async(self.middleware, scope, call_next)
            else:
                await call_next()

        return wrapped


__all__ = ["DjangoMiddlewareASGIAdapter"]
