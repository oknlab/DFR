"""DRF-style throttling adapter helpers."""

from __future__ import annotations

from typing import Any

from dfr.throttling.base import BaseThrottle


class DRFThrottleAdapter:
    """Adapter to expose BaseThrottle through DRF-compatible call signature."""

    def __init__(self, throttle: BaseThrottle) -> None:
        self.throttle = throttle

    async def allow_request(self, request: Any, view: Any | None = None) -> bool:
        ident = getattr(request, "client", None) or getattr(request, "ident", "anon")
        return await self.throttle.allow_request(request, str(ident))


__all__ = ["DRFThrottleAdapter"]
