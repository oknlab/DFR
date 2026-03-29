"""Dependency injection bridge for DFR.

This module provides a FastAPI-style ``Depends`` marker and a request-scoped
container for dependency resolution in a Django-aware runtime.

Example:
    from dfr.deps import Depends, get_container

    async def current_tenant(request) -> str:
        return request.headers.get("x-tenant", "default")

    dependency = Depends(current_tenant)
    value = await get_container().resolve(request, dependency)
"""

from __future__ import annotations

import inspect
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Generic, TypeVar

from dfr.sync import run_sync
from dfr.types import RequestLike

__all__ = [
    "Depends",
    "Dependency",
    "DependencyError",
    "DependencyLifetime",
    "DependencyProvider",
    "RequestScope",
    "get_container",
]

T = TypeVar("T")


class DependencyError(RuntimeError):
    """Raised when dependency resolution fails."""


class DependencyLifetime(str, Enum):
    """Provider lifetime modes."""

    REQUEST = "request"
    SINGLETON = "singleton"
    TRANSIENT = "transient"


@dataclass(slots=True, frozen=True)
class Dependency(Generic[T]):
    """Marker object analogous to FastAPI's ``Depends``.

    Args:
        dependency: Callable provider.
        use_cache: Reuse cached request value when True.

    Example:
        async def get_user(request):
            return request.user

        dep = Depends(get_user)
    """

    dependency: Callable[..., Any]
    use_cache: bool = True


def Depends(dependency: Callable[..., Any], *, use_cache: bool = True) -> Dependency[Any]:
    """Create a DFR dependency marker.

    Args:
        dependency: Provider callable.
        use_cache: Cache request-scoped result.
    """

    return Dependency(dependency=dependency, use_cache=use_cache)


@dataclass(slots=True)
class DependencyProvider:
    """Registry record for a named provider."""

    factory: Callable[..., Any]
    lifetime: DependencyLifetime


@dataclass(slots=True)
class RequestScope:
    """Per-request dependency cache and teardown stack."""

    cache: dict[Callable[..., Any], Any]
    exit_stack: AsyncExitStack


class DIContainer:
    """Dependency injection container with request lifecycle integration.

    Example:
        container = get_container()
        container.register("settings", lambda: {...}, lifetime=DependencyLifetime.SINGLETON)
    """

    def __init__(self) -> None:
        self._providers: dict[str, DependencyProvider] = {}
        self._singletons: dict[str, Any] = {}

    def register(self, name: str, factory: Callable[..., Any], *, lifetime: DependencyLifetime) -> None:
        """Register provider by name."""

        if not name:
            raise DependencyError("Provider name cannot be empty. Supply a stable key like 'current_user'.")
        self._providers[name] = DependencyProvider(factory=factory, lifetime=lifetime)

    async def resolve(self, request: RequestLike, dep: Dependency[T]) -> T:
        """Resolve a dependency for the current request."""

        scope = await self._get_scope(request)
        provider = dep.dependency

        if dep.use_cache and provider in scope.cache:
            return scope.cache[provider]

        value = await self._invoke_provider(request, provider)
        if dep.use_cache:
            scope.cache[provider] = value
        return value

    async def resolve_named(self, request: RequestLike, name: str) -> Any:
        """Resolve a named provider by lifetime policy."""

        provider = self._providers.get(name)
        if provider is None:
            raise DependencyError(f"Unknown provider '{name}'. Register it before resolution.")

        if provider.lifetime is DependencyLifetime.SINGLETON:
            if name not in self._singletons:
                self._singletons[name] = await self._invoke_provider(request, provider.factory)
            return self._singletons[name]

        if provider.lifetime is DependencyLifetime.TRANSIENT:
            return await self._invoke_provider(request, provider.factory)

        scope = await self._get_scope(request)
        if name in scope.cache:
            return scope.cache[name]

        value = await self._invoke_provider(request, provider.factory)
        scope.cache[name] = value
        return value

    async def start_request(self, request: RequestLike) -> RequestScope:
        """Initialize request dependency scope."""

        state = _ensure_state(request)
        scope = RequestScope(cache={}, exit_stack=AsyncExitStack())
        await scope.exit_stack.__aenter__()
        setattr(state, "_dfr_di_scope", scope)
        return scope

    async def end_request(self, request: RequestLike) -> None:
        """Tear down request dependency scope."""

        state = _ensure_state(request)
        scope = getattr(state, "_dfr_di_scope", None)
        if scope is None:
            return
        await scope.exit_stack.aclose()
        delattr(state, "_dfr_di_scope")

    async def _get_scope(self, request: RequestLike) -> RequestScope:
        state = _ensure_state(request)
        scope = getattr(state, "_dfr_di_scope", None)
        if scope is None:
            scope = await self.start_request(request)
        return scope

    async def _invoke_provider(self, request: RequestLike, provider: Callable[..., Any]) -> Any:
        signature = inspect.signature(provider)
        kwargs: dict[str, Any] = {}
        if "request" in signature.parameters:
            kwargs["request"] = request

        if inspect.iscoroutinefunction(provider):
            return await provider(**kwargs)

        # FOOTGUN: calling sync providers in async context without run_sync blocks the event loop.
        return await run_sync(provider, **kwargs, thread_sensitive=False)


_CONTAINER = DIContainer()


def get_container() -> DIContainer:
    """Return process-wide DI container singleton."""

    return _CONTAINER


def _ensure_state(request: RequestLike) -> Any:
    state = getattr(request, "state", None)
    if state is None:
        raise DependencyError(
            "Request object has no 'state' attribute. Ensure middleware initializes a request.state namespace."
        )
    return state
