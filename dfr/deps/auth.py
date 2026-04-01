"""Auth-focused dependency helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dfr.async_ import sync_to_async
from dfr.deps.core import Depends


class DjangoAuthDependency:
    """Run an authentication backend chain and return the first authenticated user."""

    def __init__(self, backends: list[Callable[[Any], Any]] | None = None) -> None:
        self.backends = backends or []

    async def __call__(self, request: Any) -> Any | None:
        for backend in self.backends:
            candidate = backend(request)
            if hasattr(candidate, "__await__"):
                candidate = await candidate
            if candidate is not None:
                return candidate
        return None


class DjangoSessionAuthDependency:
    """Authenticate user from Django-like session storage."""

    def __init__(self, user_loader: Callable[[Any], Any], session_key: str = "_auth_user_id") -> None:
        self.user_loader = user_loader
        self.session_key = session_key

    async def __call__(self, request: Any) -> Any | None:
        session = getattr(request, "session", None)
        if session is None:
            return None
        user_id = session.get(self.session_key)
        if user_id is None:
            return None
        user = self.user_loader(user_id)
        if hasattr(user, "__await__"):
            user = await user
        return user


class RequireAuthenticatedUser:
    """Ensure a user is available after auth backend evaluation."""

    def __init__(self, auth_dependency: DjangoAuthDependency) -> None:
        self.auth_dependency = auth_dependency

    async def __call__(self, request: Any) -> Any:
        user = await self.auth_dependency(request)
        if user is None:
            raise PermissionError("Authentication required.")
        return user


def current_user_dependency(*, required: bool = True) -> Depends:
    """Return a dependency that extracts `request.user`.

    Raises `PermissionError` when required and missing.
    """

    async def _resolve(request: Any) -> Any:
        user = await sync_to_async(getattr, request, "user", None)
        if required and user is None:
            raise PermissionError("Authentication required but request.user is missing.")
        return user

    return Depends(_resolve)


__all__ = ["DjangoAuthDependency", "DjangoSessionAuthDependency", "RequireAuthenticatedUser", "current_user_dependency"]
