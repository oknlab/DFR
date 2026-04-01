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


__all__ = ["DjangoAuthDependency", "RequireAuthenticatedUser", "current_user_dependency"]
