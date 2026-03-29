"""Throttling policies and async cache backends for DFR."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol

from django.conf import settings

from dfr.permissions import DFRRequestAdapter
from dfr.sync import run_sync

__all__ = [
    "AnonRateThrottle",
    "AsyncThrottle",
    "BaseThrottle",
    "DjangoCacheThrottleBackend",
    "InMemoryThrottleBackend",
    "SimpleRateThrottle",
    "ThrottledError",
    "ThrottleCacheBackend",
    "UserRateThrottle",
    "check_throttles",
    "check_throttles_async",
]


class ThrottledError(RuntimeError):
    """Raised when request exceeds throttle rate."""

    def __init__(self, message: str, *, wait: float | None = None) -> None:
        super().__init__(message)
        self.wait = wait


class ThrottleCacheBackend(Protocol):
    """Async cache backend protocol for throttling state."""

    async def get(self, key: str) -> Any:
        ...

    async def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        ...


class DjangoCacheThrottleBackend:
    """Django cache adapter for throttle state."""

    async def get(self, key: str) -> Any:
        from django.core.cache import cache

        # FOOTGUN: Django cache backend methods are sync and can block I/O in async contexts.
        return await run_sync(cache.get, key, thread_sensitive=True)

    async def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        from django.core.cache import cache

        # FOOTGUN: Django cache backend methods are sync and can block I/O in async contexts.
        await run_sync(cache.set, key, value, timeout, thread_sensitive=True)


class InMemoryThrottleBackend:
    """In-memory throttle backend for local development and tests."""

    def __init__(self) -> None:
        self._storage: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        async with self._lock:
            existing = self._storage.get(key)
            if existing is None:
                return None
            value, expires_at = existing
            if expires_at is not None and expires_at < time.time():
                del self._storage[key]
                return None
            return value

    async def set(self, key: str, value: Any, timeout: int | None = None) -> None:
        async with self._lock:
            expires = None if timeout is None else time.time() + timeout
            self._storage[key] = (value, expires)


class BaseThrottle:
    """DRF-compatible throttle base class."""

    def __init__(self) -> None:
        self.history: list[float] = []
        self.num_requests = 0
        self.duration = 0

    def allow_request(self, request: DFRRequestAdapter, view: Any) -> bool:
        return True

    def wait(self) -> float | None:
        if not self.history or self.num_requests <= 0:
            return None
        remaining = self.duration - (time.time() - self.history[-1])
        return max(remaining, 0.0)


class AsyncThrottle(Protocol):
    """Async-native throttle protocol."""

    async def allow_request(self, request: DFRRequestAdapter, view: Any) -> bool:
        ...

    def wait(self) -> float | None:
        ...


class SimpleRateThrottle(BaseThrottle):
    """Rate throttle with sliding window using async cache backend."""

    scope = "default"

    def __init__(self, *, rate: str, cache_backend: ThrottleCacheBackend | None = None) -> None:
        super().__init__()
        self.rate = rate
        self.num_requests, self.duration = self.parse_rate(rate)
        self.cache = cache_backend or _default_cache_backend()

    @staticmethod
    def parse_rate(rate: str) -> tuple[int, int]:
        count_str, period = rate.split("/", 1)
        count = int(count_str)
        period = period.strip().lower()
        durations = {
            "sec": 1,
            "second": 1,
            "min": 60,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }
        if period not in durations:
            raise ValueError(f"Unsupported rate period '{period}'. Use sec/min/hour/day.")
        return count, durations[period]

    def get_cache_key(self, request: DFRRequestAdapter, view: Any) -> str | None:
        return None

    async def allow_request(self, request: DFRRequestAdapter, view: Any) -> bool:
        key = self.get_cache_key(request, view)
        if key is None:
            return True

        now = time.time()
        history = await self.cache.get(key)
        if not isinstance(history, list):
            history = []

        history = [ts for ts in history if ts > now - self.duration]
        self.history = history
        if len(history) >= self.num_requests:
            await self.cache.set(key, history, self.duration)
            return False

        history.insert(0, now)
        self.history = history
        await self.cache.set(key, history, self.duration)
        return True


class UserRateThrottle(SimpleRateThrottle):
    """Throttle keyed by authenticated user id."""

    scope = "user"

    def __init__(self, *, rate: str | None = None, cache_backend: ThrottleCacheBackend | None = None) -> None:
        configured = rate or _get_rate_for_scope("user", default="100/min")
        super().__init__(rate=configured, cache_backend=cache_backend)

    def get_cache_key(self, request: DFRRequestAdapter, view: Any) -> str | None:
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        return f"throttle:{self.scope}:{getattr(user, 'pk', 'unknown')}"


class AnonRateThrottle(SimpleRateThrottle):
    """Throttle keyed by request client IP."""

    scope = "anon"

    def __init__(self, *, rate: str | None = None, cache_backend: ThrottleCacheBackend | None = None) -> None:
        configured = rate or _get_rate_for_scope("anon", default="20/min")
        super().__init__(rate=configured, cache_backend=cache_backend)

    def get_cache_key(self, request: DFRRequestAdapter, view: Any) -> str | None:
        user = request.user
        if user is not None and getattr(user, "is_authenticated", False):
            return None

        raw = request.raw_request
        meta = getattr(raw, "META", {})
        ip = meta.get("REMOTE_ADDR")
        if not ip:
            headers = getattr(raw, "headers", {})
            ip = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For")
            if isinstance(ip, str) and "," in ip:
                ip = ip.split(",", 1)[0].strip()
        if not ip:
            ip = "unknown"
        return f"throttle:{self.scope}:{ip}"


def check_throttles(request: Any, view: Any, throttle_classes: list[type[Any] | Any]) -> None:
    """Run sync-oriented throttle pipeline."""

    adapted = DFRRequestAdapter(request)
    for throttle in _instantiate_throttles(throttle_classes):
        if asyncio.iscoroutinefunction(getattr(throttle, "allow_request", None)):
            raise ThrottledError(
                f"Throttle '{throttle.__class__.__name__}' is async-only. Use check_throttles_async()."
            )

        allowed = throttle.allow_request(adapted, view)
        if not allowed:
            wait = throttle.wait()
            raise ThrottledError(
                f"Request throttled by '{throttle.__class__.__name__}'. Reduce request rate and retry.",
                wait=wait,
            )


async def check_throttles_async(request: Any, view: Any, throttle_classes: list[type[Any] | Any]) -> None:
    """Run async-aware throttle pipeline."""

    adapted = DFRRequestAdapter(request)
    for throttle in _instantiate_throttles(throttle_classes):
        allow = throttle.allow_request
        if asyncio.iscoroutinefunction(allow):
            allowed = await allow(adapted, view)
        else:
            # FOOTGUN: sync throttle implementations may hit sync caches; offload in async path.
            allowed = await run_sync(allow, adapted, view, thread_sensitive=True)

        if not allowed:
            wait = throttle.wait()
            raise ThrottledError(
                f"Request throttled by '{throttle.__class__.__name__}'. Reduce request rate and retry.",
                wait=wait,
            )


def _default_cache_backend() -> ThrottleCacheBackend:
    try:
        import django.core.cache  # noqa: F401

        return DjangoCacheThrottleBackend()
    except Exception:
        return InMemoryThrottleBackend()


def _get_rate_for_scope(scope: str, *, default: str) -> str:
    rates = getattr(settings, "DFR_THROTTLE_RATES", {})
    if isinstance(rates, dict) and scope in rates:
        return str(rates[scope])
    return default


def _instantiate_throttles(throttle_classes: list[type[Any] | Any]) -> list[Any]:
    instances: list[Any] = []
    for throttle in throttle_classes:
        instances.append(throttle() if isinstance(throttle, type) else throttle)
    return instances
