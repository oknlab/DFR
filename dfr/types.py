"""Shared typing primitives for DFR."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeAlias

Scope: TypeAlias = dict[str, Any]
Receive: TypeAlias = Callable[[], Awaitable[dict[str, Any]]]
Send: TypeAlias = Callable[[dict[str, Any]], Awaitable[None]]


class ASGIApp(Protocol):
    """ASGI callable contract used throughout DFR."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one ASGI connection."""


__all__ = ["ASGIApp", "Receive", "Scope", "Send"]
