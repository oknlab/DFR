"""Middleware stack management for DFR."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from dfr.exceptions import MiddlewareError
from dfr.types import Receive, Scope, Send

ASGICallable = Callable[[Scope, Receive, Send], Awaitable[None]]
MiddlewareFactory = Callable[[ASGICallable], ASGICallable]


@dataclass(slots=True)
class MiddlewareEntry:
    name: str
    factory: MiddlewareFactory


class MiddlewareStack:
    """Maintain ordered ASGI middleware around an application callable."""

    def __init__(self) -> None:
        self._entries: list[MiddlewareEntry] = []

    def add(self, name: str, factory: MiddlewareFactory) -> None:
        if any(entry.name == name for entry in self._entries):
            raise MiddlewareError(f"Middleware {name!r} is already registered.")
        self._entries.append(MiddlewareEntry(name=name, factory=factory))

    def remove(self, name: str) -> None:
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.name != name]
        if len(self._entries) == before:
            raise MiddlewareError(f"Middleware {name!r} is not registered.")

    def build(self, app: ASGICallable) -> ASGICallable:
        wrapped = app
        for entry in reversed(self._entries):
            wrapped = entry.factory(wrapped)
        return wrapped

    def names(self) -> tuple[str, ...]:
        return tuple(entry.name for entry in self._entries)


__all__ = ["MiddlewareEntry", "MiddlewareStack"]
