"""Unified middleware pipeline for DFR.

Example:
    from dfr.middleware import MiddlewareStack

    stack = MiddlewareStack()
    stack.use_django_defaults()
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from django.conf import settings

from dfr.deps import get_container
from dfr.sync import run_sync
from dfr.types import RequestLike, ResponseLike

__all__ = [
    "DjangoMiddlewareAdapter",
    "MiddlewareError",
    "MiddlewareStack",
    "RequestContext",
    "ResponseFinalizer",
    "StarletteMiddlewareAdapter",
]

DispatchCallable = Callable[[RequestLike], Awaitable[ResponseLike]]


class MiddlewareError(RuntimeError):
    """Raised when middleware setup or execution fails."""


@dataclass(slots=True)
class RequestContext:
    """Shared cross-framework context attached to ``request.state``."""

    session_committed: bool = False
    csrf_processed: bool = False
    auth_evaluated: bool = False


class DjangoMiddlewareAdapter:
    """Adapter for Django-style middleware interfaces.

    Supports callable middleware and ``process_*`` hooks.
    """

    def __init__(self, middleware: Any) -> None:
        self._middleware = middleware

    async def __call__(self, request: RequestLike, call_next: DispatchCallable) -> ResponseLike:
        process_request = getattr(self._middleware, "process_request", None)
        process_view = getattr(self._middleware, "process_view", None)
        process_exception = getattr(self._middleware, "process_exception", None)
        process_response = getattr(self._middleware, "process_response", None)

        if process_request is not None:
            response = await _call_maybe_sync(process_request, request)
            if response is not None:
                return await _finalize_django_response(process_response, request, response)

        if process_view is not None:
            # FOOTGUN: process_view hooks are sync in many Django middleware classes.
            response = await _call_maybe_sync(process_view, request, None, (), {})
            if response is not None:
                return await _finalize_django_response(process_response, request, response)

        try:
            response = await call_next(request)
        except Exception as exc:
            if process_exception is None:
                raise
            maybe_response = await _call_maybe_sync(process_exception, request, exc)
            if maybe_response is None:
                raise
            response = maybe_response

        return await _finalize_django_response(process_response, request, response)


class StarletteMiddlewareAdapter:
    """Adapter for ASGI-native middleware callables."""

    def __init__(self, middleware: Any) -> None:
        self._middleware = middleware

    async def __call__(self, request: RequestLike, call_next: DispatchCallable) -> ResponseLike:
        if inspect.iscoroutinefunction(self._middleware):
            return await self._middleware(request, call_next)

        # FOOTGUN: sync ASGI middleware must be offloaded or it blocks the event loop.
        return await run_sync(self._middleware, request, call_next, thread_sensitive=False)


class ResponseFinalizer:
    """Finalize session/CSRF state exactly once before response returns."""

    async def __call__(self, request: RequestLike, response: ResponseLike) -> ResponseLike:
        state = _ensure_state(request)
        context = _ensure_context(state)

        if not context.csrf_processed:
            setattr(state, "_csrf_processed", True)
            context.csrf_processed = True

        if context.session_committed:
            return response

        session = getattr(request, "session", None)
        if session is not None and hasattr(session, "save"):
            # FOOTGUN: Django session save is sync and can issue blocking DB/cache I/O.
            await run_sync(session.save, thread_sensitive=True)

        setattr(state, "_session_committed", True)
        context.session_committed = True
        return response


@dataclass(slots=True)
class _MiddlewareEntry:
    adapter: Any


class MiddlewareStack:
    """Single ordered middleware chain for DFR request dispatch.

    Example:
        stack = MiddlewareStack()
        stack.use_django_defaults()
        wrapped = stack.wrap(dispatch)
    """

    def __init__(self) -> None:
        self._entries: list[_MiddlewareEntry] = []
        self._finalizer = ResponseFinalizer()

    def use(self, middleware_cls: type[Any] | Callable[..., Any], **kwargs: Any) -> None:
        """Append middleware to the pipeline.

        Args:
            middleware_cls: Middleware class or callable.
            **kwargs: Constructor/config kwargs.
        """

        middleware = middleware_cls(**kwargs) if inspect.isclass(middleware_cls) else middleware_cls
        adapter = _select_adapter(middleware)
        self._entries.append(_MiddlewareEntry(adapter=adapter))

    def use_django_defaults(self) -> None:
        """Load Django ``MIDDLEWARE`` setting entries into this stack."""

        raw = getattr(settings, "MIDDLEWARE", ())
        for dotted_path in raw:
            middleware_cls = _import_string(dotted_path)
            middleware = _instantiate_django_middleware(middleware_cls)
            self._entries.append(_MiddlewareEntry(adapter=DjangoMiddlewareAdapter(middleware)))

    def wrap(self, dispatch: DispatchCallable) -> DispatchCallable:
        """Wrap dispatch callable with registered middleware chain."""

        async def _wrapped(request: RequestLike) -> ResponseLike:
            await get_container().start_request(request)
            _ensure_context(_ensure_state(request))

            call_next = dispatch
            for entry in reversed(self._entries):
                adapter = entry.adapter
                previous = call_next

                async def _layer(req: RequestLike, *, _adapter: Any = adapter, _next: DispatchCallable = previous) -> ResponseLike:
                    return await _adapter(req, _next)

                call_next = _layer

            try:
                response = await call_next(request)
                return await self._finalizer(request, response)
            finally:
                await get_container().end_request(request)

        return _wrapped


async def _call_maybe_sync(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)

    # FOOTGUN: sync middleware hooks can block request throughput if called directly in async pipeline.
    return await run_sync(func, *args, **kwargs, thread_sensitive=True)


async def _finalize_django_response(
    process_response: Callable[..., Any] | None,
    request: RequestLike,
    response: ResponseLike,
) -> ResponseLike:
    if process_response is None:
        return response
    return await _call_maybe_sync(process_response, request, response)


def _instantiate_django_middleware(middleware_cls: type[Any]) -> Any:
    """Instantiate Django middleware class with fallback get_response."""

    def _terminal(_request: RequestLike) -> Any:
        return None

    try:
        return middleware_cls(_terminal)
    except TypeError as exc:
        raise MiddlewareError(
            f"Failed to initialize Django middleware '{middleware_cls.__module__}.{middleware_cls.__name__}'. "
            "Ensure it accepts get_response in constructor."
        ) from exc


def _select_adapter(middleware: Any) -> Any:
    if any(hasattr(middleware, attr) for attr in ("process_request", "process_view", "process_response", "process_exception")):
        return DjangoMiddlewareAdapter(middleware)
    return StarletteMiddlewareAdapter(middleware)


def _import_string(path: str) -> Any:
    if "." not in path:
        raise MiddlewareError(f"Invalid middleware path '{path}'. Use fully qualified module path.")
    module_name, attr = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise MiddlewareError(f"Cannot import '{attr}' from '{module_name}'. Check Django MIDDLEWARE setting.") from exc


def _ensure_state(request: RequestLike) -> Any:
    state = getattr(request, "state", None)
    if state is None:
        state = SimpleNamespace()
        setattr(request, "state", state)
    return state


def _ensure_context(state: Any) -> RequestContext:
    existing = getattr(state, "_dfr_context", None)
    if existing is not None:
        return existing
    context = RequestContext()
    setattr(state, "_dfr_context", context)
    return context
