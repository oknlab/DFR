"""Auth-focused dependency helpers."""

from __future__ import annotations

from typing import Any

from dfr.deps.core import Depends


def current_user_dependency(*, required: bool = True) -> Depends:
    """Return a dependency that extracts `request.user`.

    Raises `PermissionError` when required and missing.
    """

    async def _resolve(request: Any) -> Any:
        user = getattr(request, "user", None)
        if required and user is None:
            raise PermissionError("Authentication required but request.user is missing.")
        return user

    return Depends(_resolve)


__all__ = ["current_user_dependency"]
