from __future__ import annotations

import asyncio
import importlib.util

import pytest


def test_run_sync_smoke() -> None:
    if importlib.util.find_spec("asgiref") is None:
        pytest.skip("asgiref not installed")

    from dfr.sync import ExecutorConfig, configure_executors, run_sync

    configure_executors(ExecutorConfig(max_db_offloads=2, cpu_workers=1, use_process_pool=False))

    async def _runner() -> int:
        return await run_sync(lambda: 41 + 1)

    result = asyncio.run(_runner())
    assert result == 42
