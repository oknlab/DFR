"""Unified sync/async test client wrappers."""

from __future__ import annotations

import asyncio
from typing import Any


class DFRTestClient:
    """Small adapter that supports sync and async invocation styles."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def request_async(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)

        await self.app(scope, receive, send)
        return messages

    def request(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        return asyncio.run(self.request_async(scope))


__all__ = ["DFRTestClient"]
