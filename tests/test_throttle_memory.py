from __future__ import annotations

import asyncio
import importlib.util

import pytest


def test_inmemory_throttle_backend_expiry() -> None:
    if importlib.util.find_spec("django") is None or importlib.util.find_spec("asgiref") is None:
        pytest.skip("django/asgiref not installed")

    from dfr.throttling import InMemoryThrottleBackend

    backend = InMemoryThrottleBackend()

    async def _runner() -> None:
        await backend.set("k", [1], timeout=0)
        value = await backend.get("k")
        assert value is None

    asyncio.run(_runner())
