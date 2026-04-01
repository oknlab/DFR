"""Simple cache-backed throttling primitives."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class BaseThrottle:
    """In-memory throttle base with rate syntax '<count>/<window>s|m|h'."""

    rate = "60/m"

    def __init__(self) -> None:
        self._history: dict[str, list[float]] = defaultdict(list)

    def parse_rate(self) -> tuple[int, int]:
        count_s, window_s = self.rate.split("/")
        count = int(count_s)
        unit = window_s.strip().lower()
        seconds = {"s": 1, "m": 60, "h": 3600}[unit]
        return count, seconds

    async def allow_request(self, request: Any, ident: str) -> bool:
        count, window = self.parse_rate()
        now = time.time()
        history = [t for t in self._history[ident] if now - t < window]
        if len(history) >= count:
            self._history[ident] = history
            return False
        history.append(now)
        self._history[ident] = history
        return True


__all__ = ["BaseThrottle"]
