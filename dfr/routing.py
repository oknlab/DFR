"""Unified routing registry and dispatcher for DFR.

This module provides a canonical route registry that merges DFR, FastAPI,
and Django endpoints into one normalized table.

Example:
    from dfr.routing import route, get_registry

    @route("GET", "/health")
    async def health(request) -> dict[str, str]:
        return {"status": "ok"}

    registry = get_registry()
    registry.finalize()
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Sequence

from dfr.sync import run_sync
from dfr.types import HandlerType, HTTPHandler, RouteEntry

__all__ = [
    "DispatchError",
    "RouteConflictError",
    "RouteMatch",
    "RouteRegistry",
    "finalize_routes",
    "get_registry",
    "include_django_urls",
    "include_router",
    "route",
]

_TYPED_SEGMENT_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-zA-Z_][a-zA-Z0-9_]*))?\}")
_DJANGO_CONVERTER_RE = re.compile(r"<([a-zA-Z_][a-zA-Z0-9_]*):([a-zA-Z_][a-zA-Z0-9_]*)>")


class RouteConflictError(RuntimeError):
    """Raised when conflicting route definitions cannot be resolved."""


class DispatchError(RuntimeError):
    """Raised when a request cannot be dispatched to a valid handler."""


@dataclass(slots=True, frozen=True)
class _NormalizedPath:
    canonical: str
    rank: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class RouteMatch:
    """Result object for path-method matching in RouteRegistry."""

    entry: RouteEntry
    path_params: Mapping[str, str]


class RouteRegistry:
    """Global unified route registry.

    Routes are normalized to a canonical form so Django and Starlette/FastAPI
    path syntaxes can coexist and conflict detection can be deterministic.

    Example:
        registry = RouteRegistry()
        registry.register(
            path="/items/{item_id:int}",
            methods={"GET"},
            handler=handler,
            handler_type=HandlerType.DFR_VIEW,
        )
        registry.finalize()
    """

    def __init__(self) -> None:
        self._entries: list[RouteEntry] = []
        self._finalized: bool = False

    def register(
        self,
        *,
        path: str,
        methods: Iterable[str],
        handler: HTTPHandler,
        handler_type: HandlerType,
        name: str | None = None,
        priority: int = 0,
        source: str | None = None,
        tags: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RouteEntry:
        """Register a route in canonical form.

        Raises:
            RouteConflictError: If conflict is detected and cannot be resolved.
        """

        if self._finalized:
            raise RouteConflictError(
                "Cannot register routes after finalize(). Register routes before DFRApp.bootstrap() route finalization phase."
            )

        normalized = self._normalize_path(path)
        entry = RouteEntry(
            path=normalized.canonical,
            methods=frozenset(method.upper() for method in methods),
            handler=handler,
            handler_type=handler_type,
            name=name,
            priority=priority,
            source=source,
            tags=tuple(tags or ()),
            metadata=metadata or {},
        )
        self._assert_no_unresolved_conflict(entry)
        self._entries.append(entry)
        return entry

    def finalize(self) -> None:
        """Finalize routing table and lock registration."""

        self._detect_all_conflicts()
        self._finalized = True

    @property
    def entries(self) -> tuple[RouteEntry, ...]:
        """Return immutable route entry snapshot."""

        return tuple(self._entries)

    def match(self, path: str, method: str) -> RouteMatch | None:
        """Find the best route entry for a request path and method."""

        normalized = self._normalize_path(path)
        method_upper = method.upper()

        candidates: list[tuple[tuple[int, ...], int, RouteEntry]] = []
        for entry in self._entries:
            if method_upper not in entry.methods:
                continue
            if not self._path_equivalent(entry.path, normalized.canonical):
                continue
            candidates.append((self._rank_path(entry.path), entry.priority, entry))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        top = candidates[0][2]
        params = self._extract_path_params(top.path, normalized.canonical)
        return RouteMatch(entry=top, path_params=params)

    async def dispatch(self, *, request: Any, path: str, method: str) -> Any:
        """Dispatch request to matched handler with sync/async awareness.

        Raises:
            DispatchError: If no route matches.
        """

        match = self.match(path, method)
        if match is None:
            raise DispatchError(
                f"No route matched {method.upper()} {path}. Confirm route registration and trailing slash policy."
            )

        handler = match.entry.handler
        if inspect.iscoroutinefunction(handler):
            return await handler(request=request, **match.path_params)

        # FOOTGUN: invoking sync Django handlers directly in event loop blocks all async requests.
        return await run_sync(handler, request, **match.path_params, thread_sensitive=True)

    def _detect_all_conflicts(self) -> None:
        seen: list[RouteEntry] = []
        for entry in self._entries:
            for other in seen:
                self._assert_conflict_pair(entry, other)
            seen.append(entry)

    def _assert_no_unresolved_conflict(self, entry: RouteEntry) -> None:
        for existing in self._entries:
            self._assert_conflict_pair(entry, existing)

    def _assert_conflict_pair(self, left: RouteEntry, right: RouteEntry) -> None:
        if left is right:
            return
        if left.methods.isdisjoint(right.methods):
            return
        if not self._path_equivalent(left.path, right.path):
            return

        left_rank = self._rank_path(left.path)
        right_rank = self._rank_path(right.path)

        if left_rank == right_rank and left.priority == right.priority:
            left_src = left.source or "<unknown source>"
            right_src = right.source or "<unknown source>"
            raise RouteConflictError(
                "Route conflict detected between "
                f"{left.methods} {left.path} ({left_src}) and {right.methods} {right.path} ({right_src}). "
                "Set explicit priority= on one registration to break the tie."
            )

    @staticmethod
    def _normalize_path(path: str) -> _NormalizedPath:
        canonical = path.strip()
        if not canonical.startswith("/"):
            canonical = f"/{canonical}"

        canonical = _DJANGO_CONVERTER_RE.sub(lambda m: f"{{{m.group(2)}:{m.group(1)}}}", canonical)
        canonical = _TYPED_SEGMENT_RE.sub(
            lambda m: f"{{{m.group(1)}:{(m.group(2) or 'str').lower()}}}",
            canonical,
        )
        if canonical != "/" and canonical.endswith("/"):
            canonical = canonical.rstrip("/")

        rank = RouteRegistry._rank_path(canonical)
        return _NormalizedPath(canonical=canonical, rank=rank)

    @staticmethod
    def _rank_path(path: str) -> tuple[int, ...]:
        ranks: list[int] = []
        for segment in [seg for seg in path.split("/") if seg]:
            if segment.startswith("{") and segment.endswith("}"):
                token = segment[1:-1]
                if token.startswith("*"):
                    ranks.append(1)  # wildcard
                else:
                    ranks.append(2)  # typed param
            else:
                ranks.append(3)  # static
        return tuple(ranks)

    @staticmethod
    def _path_equivalent(left: str, right: str) -> bool:
        left_segments = [seg for seg in left.split("/") if seg]
        right_segments = [seg for seg in right.split("/") if seg]
        if len(left_segments) != len(right_segments):
            return False

        for l_seg, r_seg in zip(left_segments, right_segments, strict=True):
            l_typed = l_seg.startswith("{") and l_seg.endswith("}")
            r_typed = r_seg.startswith("{") and r_seg.endswith("}")
            if l_typed and r_typed:
                continue
            if l_seg != r_seg:
                return False
        return True

    @staticmethod
    def _extract_path_params(pattern: str, actual: str) -> dict[str, str]:
        params: dict[str, str] = {}
        p_segments = [seg for seg in pattern.split("/") if seg]
        a_segments = [seg for seg in actual.split("/") if seg]
        for p_seg, a_seg in zip(p_segments, a_segments, strict=False):
            if not (p_seg.startswith("{") and p_seg.endswith("}")):
                continue
            token = p_seg[1:-1]
            name = token.split(":", 1)[0]
            params[name] = a_seg
        return params


_registry = RouteRegistry()


def get_registry() -> RouteRegistry:
    """Return the process-wide routing registry singleton."""

    return _registry


def finalize_routes() -> None:
    """Finalize global registry for DFR bootstrap integration."""

    _registry.finalize()


def route(
    method: str,
    path: str,
    *,
    name: str | None = None,
    priority: int = 0,
    tags: Sequence[str] | None = None,
) -> Callable[[HTTPHandler], HTTPHandler]:
    """Register a DFR-native route decorator.

    Example:
        @route("GET", "/health", tags=["system"])
        async def health(request) -> dict[str, str]:
            return {"status": "ok"}
    """

    def decorator(handler: HTTPHandler) -> HTTPHandler:
        src = f"{getattr(handler, '__module__', '<module>')}.{getattr(handler, '__qualname__', '<handler>')}"
        _registry.register(
            path=path,
            methods={method},
            handler=handler,
            handler_type=HandlerType.DFR_VIEW,
            name=name,
            priority=priority,
            source=src,
            tags=tags,
        )
        return handler

    return decorator


def include_router(router: Any, *, prefix: str = "", priority: int = 0) -> None:
    """Import routes from a FastAPI APIRouter-like object.

    The router must expose a ``routes`` iterable with members containing
    ``path``, ``methods``, and ``endpoint`` attributes.
    """

    routes = getattr(router, "routes", None)
    if routes is None:
        raise TypeError("include_router() expected an object with .routes. Pass a FastAPI APIRouter instance.")

    for item in routes:
        path = f"{prefix}{getattr(item, 'path', '')}"
        methods = getattr(item, "methods", None)
        endpoint = getattr(item, "endpoint", None)
        if not path or methods is None or endpoint is None:
            continue

        source = f"{getattr(endpoint, '__module__', '<module>')}.{getattr(endpoint, '__qualname__', '<handler>')}"
        _registry.register(
            path=path,
            methods={str(m) for m in methods},
            handler=endpoint,
            handler_type=HandlerType.FASTAPI_ROUTE,
            name=getattr(item, "name", None),
            priority=priority,
            source=source,
            tags=tuple(getattr(item, "tags", ()) or ()),
            metadata={"router": router.__class__.__name__},
        )


def include_django_urls(patterns: Sequence[Any], *, prefix: str = "", priority: int = 0) -> None:
    """Import Django URL patterns or tuple declarations into the registry.

    Accepted input forms:
        1. Django URLPattern-like object with ``pattern``, ``callback``, ``name``.
        2. Tuple: (path: str, handler: callable, name: str | None).
    """

    for item in patterns:
        if isinstance(item, tuple):
            raw_path = str(item[0])
            handler = item[1]
            name = str(item[2]) if len(item) > 2 and item[2] is not None else None
            source = f"{getattr(handler, '__module__', '<module>')}.{getattr(handler, '__qualname__', '<handler>')}"
            _registry.register(
                path=f"{prefix}{raw_path}",
                methods={"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"},
                handler=handler,
                handler_type=HandlerType.DJANGO_VIEW,
                name=name,
                priority=priority,
                source=source,
                metadata={"origin": "tuple"},
            )
            continue

        callback = getattr(item, "callback", None)
        pattern = getattr(item, "pattern", None)
        if callback is None or pattern is None:
            continue

        raw_path = getattr(pattern, "_route", None) or str(pattern)
        entry_name = getattr(item, "name", None)
        source = f"{getattr(callback, '__module__', '<module>')}.{getattr(callback, '__qualname__', '<handler>')}"
        _registry.register(
            path=f"{prefix}{raw_path}",
            methods={"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"},
            handler=callback,
            handler_type=HandlerType.DJANGO_VIEW,
            name=str(entry_name) if entry_name else None,
            priority=priority,
            source=source,
            metadata={"origin": "django_urlpattern"},
        )


# Export a minimal object for future app bootstrap hook wiring.
ROUTING_HOOKS = SimpleNamespace(finalize=finalize_routes)
