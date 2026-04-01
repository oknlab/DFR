"""Database/session dependencies."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable


@asynccontextmanager
async def transaction(opener: Callable[[], object]) -> AsyncIterator[object]:
    """Async transaction context manager wrapper."""
    conn = opener()
    try:
        yield conn
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()


__all__ = ["transaction"]
