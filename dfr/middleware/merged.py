"""Merged middleware pipeline that composes native and Django-adapted middleware."""

from __future__ import annotations

from collections.abc import Callable

from dfr.middleware.django_adapter import DjangoMiddlewareASGIAdapter
from dfr.middleware.stack import ASGICallable, MiddlewareStack


class MergedMiddlewarePipeline:
    """Compose middleware stack with optional Django middleware adapters."""

    def __init__(self) -> None:
        self.stack = MiddlewareStack()

    def add_native(self, name: str, factory: Callable[[ASGICallable], ASGICallable]) -> None:
        self.stack.add(name, factory)

    def add_django(self, name: str, middleware_callable) -> None:
        adapter = DjangoMiddlewareASGIAdapter(middleware_callable)
        self.stack.add(name, adapter.wrap)

    def build(self, app: ASGICallable) -> ASGICallable:
        return self.stack.build(app)


__all__ = ["MergedMiddlewarePipeline"]
