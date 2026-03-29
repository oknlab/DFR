"""Shared protocols, aliases, and enums for DFR.

This module exists to prevent circular imports across core modules.

Example:
    from dfr.types import HandlerType, RouteEntry

    entry = RouteEntry(
        path="/health",
        methods=frozenset({"GET"}),
        handler=lambda request: {"ok": True},
        handler_type=HandlerType.DFR_VIEW,
        name="health",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypeAlias, runtime_checkable

__all__ = [
    "ASGIApp",
    "ASGIReceive",
    "ASGIScope",
    "ASGISend",
    "AuthResult",
    "AuthToken",
    "DFRBootPhase",
    "DispatchCallable",
    "HandlerType",
    "HTTPHandler",
    "Method",
    "PathLike",
    "RequestLike",
    "ResponseLike",
    "RouteEntry",
    "SupportsAuthenticate",
    "SupportsBootstrap",
]

ASGIScope: TypeAlias = dict[str, Any]
ASGIReceive: TypeAlias = Any
ASGISend: TypeAlias = Any
ASGIApp: TypeAlias = Any

Method: TypeAlias = str
PathLike: TypeAlias = str
DispatchCallable: TypeAlias = Any
RequestLike: TypeAlias = Any
ResponseLike: TypeAlias = Any
AuthToken: TypeAlias = str | None
AuthResult: TypeAlias = tuple[Any | None, AuthToken]


class HandlerType(str, Enum):
    """Route origin in the unified registry."""

    DJANGO_VIEW = "django_view"
    DFR_VIEW = "dfr_view"
    FASTAPI_ROUTE = "fastapi_route"


class DFRBootPhase(str, Enum):
    """Lifecycle phase for DFR application bootstrapping."""

    CREATED = "created"
    DJANGO_INITIALIZED = "django_initialized"
    ROUTES_FINALIZED = "routes_finalized"
    READY = "ready"


@runtime_checkable
class HTTPHandler(Protocol):
    """Protocol for sync/async HTTP handlers registered in DFR."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        ...


@runtime_checkable
class SupportsAuthenticate(Protocol):
    """Protocol for auth backends used by DFR dependencies."""

    async def authenticate(self, request: RequestLike) -> AuthResult:
        """Authenticate a request and return (user, token)."""


@runtime_checkable
class SupportsBootstrap(Protocol):
    """Protocol for components that require explicit bootstrap."""

    def bootstrap(self) -> None:
        """Initialize component resources."""


@dataclass(slots=True, frozen=True)
class RouteEntry:
    """Canonical route registration object.

    Attributes:
        path: Canonical path pattern.
        methods: Allowed HTTP methods in uppercase.
        handler: Callable endpoint.
        handler_type: Route origin enum.
        name: Optional route name.
        priority: Conflict tie-breaker.
        source: Optional source location string.
        tags: OpenAPI tags.
        metadata: Arbitrary adapter metadata.
    """

    path: str
    methods: frozenset[str]
    handler: HTTPHandler
    handler_type: HandlerType
    name: str | None = None
    priority: int = 0
    source: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
