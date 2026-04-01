"""Async/sync boundary helpers for DFR.

These wrappers centralize threadpool policy so routing, serializers, and
middleware can share one executor strategy.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class ORMExecutor:
    """Threadpool container used for sync Django ORM operations.

    Example:
        >>> executor = ORMExecutor(max_workers=16)
        >>> await executor.run(lambda: 1)
        1
    """

    max_workers: int = 16
    _executor: ThreadPoolExecutor = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="dfr-orm")

    async def run(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a sync callable in the ORM threadpool."""
        loop = asyncio.get_running_loop()
        bound = partial(func, *args, **kwargs)
        return await loop.run_in_executor(self._executor, bound)

    def shutdown(self) -> None:
        """Shutdown the executor for tests/process teardown."""
        self._executor.shutdown(wait=True)


_default_executor = ORMExecutor()


async def sync_to_async(func: Callable[..., T], *args: Any, executor: ORMExecutor | None = None, **kwargs: Any) -> T:
    """Run a sync function asynchronously using the DFR ORM executor."""
    selected = executor if executor is not None else _default_executor
    return await selected.run(func, *args, **kwargs)


def async_to_sync(func: Callable[..., Any]) -> Callable[..., Any]:
    """Expose an async callable through a sync interface."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(func(*args, **kwargs))

    return wrapper


__all__ = ["ORMExecutor", "async_to_sync", "sync_to_async"]
