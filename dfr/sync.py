"""Async/sync boundary utilities for DFR.

Example:
    from dfr.sync import run_sync

    async def get_count() -> int:
        # One coarse boundary around sync ORM access.
        return await run_sync(lambda: User.objects.count())
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, ParamSpec, TypeVar

from asgiref.sync import sync_to_async

__all__ = [
    "BoundaryViolationError",
    "ExecutorConfig",
    "configure_executors",
    "cpu_bound",
    "run_sync",
]

P = ParamSpec("P")
R = TypeVar("R")

_boundary_depth: ContextVar[int] = ContextVar("dfr_boundary_depth", default=0)
_db_semaphore: asyncio.Semaphore | None = None
_cpu_pool: ProcessPoolExecutor | ThreadPoolExecutor | None = None


class BoundaryViolationError(RuntimeError):
    """Raised when an invalid nested async/sync boundary is detected."""


@dataclass(slots=True)
class ExecutorConfig:
    """Configuration for DFR sync/async boundary executors.

    Attributes:
        max_db_offloads: Max concurrent DB-bound sync offloads per worker.
        cpu_workers: Number of CPU pool workers.
        use_process_pool: Use process pool for CPU-bound tasks when True.

    Example:
        configure_executors(ExecutorConfig(max_db_offloads=64, cpu_workers=4))
    """

    max_db_offloads: int = 64
    cpu_workers: int = 4
    use_process_pool: bool = True


def configure_executors(config: ExecutorConfig) -> None:
    """Configure executor resources used by DFR boundary utilities.

    Args:
        config: Executor and backpressure settings.
    """

    global _db_semaphore, _cpu_pool
    if config.max_db_offloads < 1:
        raise ValueError("max_db_offloads must be >= 1; increase it to avoid deadlocks.")
    if config.cpu_workers < 1:
        raise ValueError("cpu_workers must be >= 1; set at least one worker.")

    _db_semaphore = asyncio.Semaphore(config.max_db_offloads)

    if _cpu_pool is not None:
        _cpu_pool.shutdown(wait=False, cancel_futures=True)

    if config.use_process_pool:
        _cpu_pool = ProcessPoolExecutor(max_workers=config.cpu_workers)
    else:
        _cpu_pool = ThreadPoolExecutor(max_workers=config.cpu_workers, thread_name_prefix="dfr-cpu")


async def run_sync(fn: Callable[P, R], *args: P.args, thread_sensitive: bool = True, **kwargs: P.kwargs) -> R:
    """Run sync work from async code with boundary safeguards.

    Args:
        fn: Synchronous callable to execute.
        *args: Callable positional args.
        thread_sensitive: Route operation through thread-sensitive executor.
        **kwargs: Callable keyword args.

    Returns:
        Result from ``fn``.

    Raises:
        BoundaryViolationError: If called inside an already active DFR boundary.

    Example:
        async def fetch_user(user_id: int) -> User:
            # FOOTGUN: do not wrap each queryset operation separately.
            return await run_sync(User.objects.select_related("profile").get, id=user_id)
    """

    current_depth = _boundary_depth.get()
    if current_depth > 0:
        raise BoundaryViolationError(
            "Nested sync boundary detected. Consolidate ORM work into one run_sync() block to avoid deadlocks."
        )

    semaphore = _db_semaphore
    if semaphore is None:
        configure_executors(ExecutorConfig())
        semaphore = _db_semaphore
        assert semaphore is not None

    token = _boundary_depth.set(current_depth + 1)
    try:
        async with semaphore:
            # FOOTGUN: Calling async_to_sync(sync_to_async(...)) in same call chain can deadlock.
            bound_fn = partial(fn, *args, **kwargs)
            return await sync_to_async(bound_fn, thread_sensitive=thread_sensitive)()
    finally:
        _boundary_depth.reset(token)


async def cpu_bound(fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    """Execute CPU-bound sync work off the event loop.

    Args:
        fn: CPU-heavy callable.
        *args: Callable positional args.
        **kwargs: Callable keyword args.

    Returns:
        Callable result.
    """

    pool = _cpu_pool
    if pool is None:
        configure_executors(ExecutorConfig())
        pool = _cpu_pool
        assert pool is not None

    loop = asyncio.get_running_loop()
    call = partial(fn, *args, **kwargs)
    # FOOTGUN: CPU work on event loop will starve all in-flight requests.
    return await loop.run_in_executor(pool, call)
