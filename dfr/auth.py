"""Authentication backends and user dependency helpers for DFR.

Example:
    from dfr.auth import CurrentUser, register_auth_backend, SessionAuthBackend
    from dfr.deps import Depends

    register_auth_backend(SessionAuthBackend(), priority=10)

    user_dep = Depends(CurrentUser.required)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from django.conf import settings

from dfr.sync import run_sync
from dfr.types import AuthResult, AuthToken, RequestLike, SupportsAuthenticate

__all__ = [
    "AuthContext",
    "AuthError",
    "CurrentUser",
    "SessionAuthBackend",
    "TokenAuthBackend",
    "get_registered_backends",
    "register_auth_backend",
]


class AuthError(RuntimeError):
    """Raised when authentication requirements are not satisfied."""


@dataclass(slots=True, frozen=True)
class AuthContext:
    """Resolved authentication context for a request.

    Attributes:
        user: Authenticated user or ``None``.
        auth_token: Token string or opaque credential identifier.
        scopes: Scope strings associated with the authenticated principal.
        backend_name: Name of backend that resolved the identity.
    """

    user: Any | None
    auth_token: AuthToken
    scopes: tuple[str, ...] = field(default_factory=tuple)
    backend_name: str = "anonymous"


@dataclass(slots=True)
class _BackendRecord:
    priority: int
    backend: SupportsAuthenticate


class SessionAuthBackend:
    """Authenticate using Django session/auth middleware state."""

    async def authenticate(self, request: RequestLike) -> AuthResult:
        from django.contrib.auth import get_user

        # FOOTGUN: django.contrib.auth.get_user is sync and may hit DB via backend.
        user = await run_sync(get_user, request, thread_sensitive=True)
        if user is None:
            return (None, None)
        if getattr(user, "is_authenticated", False):
            return (user, None)
        return (None, None)


class TokenAuthBackend:
    """Authenticate using DRF token credentials from Authorization header.

    Expected header format:
        ``Authorization: Token <key>``
    """

    async def authenticate(self, request: RequestLike) -> AuthResult:
        token = _extract_token_from_header(request)
        if token is None:
            return (None, None)

        try:
            from rest_framework.authtoken.models import Token
        except Exception as exc:
            raise AuthError(
                "TokenAuthBackend requires 'rest_framework.authtoken' in INSTALLED_APPS. "
                "Add it or unregister TokenAuthBackend."
            ) from exc

        def _resolve_user() -> Any | None:
            try:
                obj = Token.objects.select_related("user").get(key=token)
            except Token.DoesNotExist:
                return None
            return obj.user

        # FOOTGUN: ORM token lookups are sync and must be isolated via run_sync.
        user = await run_sync(_resolve_user, thread_sensitive=True)
        if user is None:
            return (None, None)
        return (user, token)


_BACKENDS: list[_BackendRecord] = []


def register_auth_backend(backend: SupportsAuthenticate, *, priority: int = 100) -> None:
    """Register an authentication backend in priority order."""

    for record in _BACKENDS:
        if record.backend.__class__ is backend.__class__:
            return

    _BACKENDS.append(_BackendRecord(priority=priority, backend=backend))
    _BACKENDS.sort(key=lambda record: record.priority)


def get_registered_backends() -> tuple[SupportsAuthenticate, ...]:
    """Return immutable ordered backend tuple."""

    return tuple(record.backend for record in _BACKENDS)


class CurrentUser:
    """Dependency helper resolving current user from registered auth backends.

    Example:
        from dfr.deps import Depends
        user_dep = Depends(CurrentUser.required)
    """

    @staticmethod
    async def optional(request: RequestLike) -> Any | None:
        """Resolve user or return ``None`` when unauthenticated."""

        context = await _resolve_auth_context(request)
        return context.user

    @staticmethod
    async def required(request: RequestLike) -> Any:
        """Resolve user and raise AuthError(401) when unavailable."""

        context = await _resolve_auth_context(request)
        if context.user is None:
            raise AuthError(
                "Authentication required. Configure session/token auth and provide valid credentials."
            )
        return context.user


async def _resolve_auth_context(request: RequestLike) -> AuthContext:
    state = _ensure_state(request)
    existing = getattr(state, "_dfr_auth", None)
    if existing is not None:
        return existing

    ordered = _ordered_backends()
    for backend in ordered:
        user, token = await backend.authenticate(request)
        if user is not None:
            context = AuthContext(
                user=user,
                auth_token=token,
                scopes=tuple(getattr(user, "scopes", ()) or ()),
                backend_name=backend.__class__.__name__,
            )
            setattr(state, "_dfr_auth", context)
            return context

    context = AuthContext(user=None, auth_token=None, scopes=(), backend_name="anonymous")
    setattr(state, "_dfr_auth", context)
    return context


def _ordered_backends() -> tuple[SupportsAuthenticate, ...]:
    order = str(getattr(settings, "DFR_AUTH_ORDER", "SESSION_FIRST")).upper()
    backends = list(_BACKENDS)

    if not backends:
        register_auth_backend(SessionAuthBackend(), priority=10)
        register_auth_backend(TokenAuthBackend(), priority=20)
        backends = list(_BACKENDS)

    if order == "TOKEN_FIRST":
        backends.sort(
            key=lambda record: (0 if record.backend.__class__.__name__.startswith("Token") else 1, record.priority)
        )
    else:
        backends.sort(
            key=lambda record: (0 if record.backend.__class__.__name__.startswith("Session") else 1, record.priority)
        )

    return tuple(record.backend for record in backends)


def _extract_token_from_header(request: RequestLike) -> str | None:
    headers = getattr(request, "headers", None)
    if headers is None:
        return None

    auth_header: str | None = None
    if isinstance(headers, dict):
        auth_header = headers.get("Authorization") or headers.get("authorization")
    else:
        auth_header = headers.get("authorization")

    if not auth_header:
        return None

    parts = auth_header.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "token":
        return None
    if not token:
        return None
    return token


def _ensure_state(request: RequestLike) -> Any:
    state = getattr(request, "state", None)
    if state is None:
        raise AuthError(
            "Request object has no 'state' attribute. Ensure middleware initializes request.state before auth resolution."
        )
    return state
