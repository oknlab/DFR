"""DRF compatibility adapters for permission classes."""

from __future__ import annotations

from typing import Any

from dfr.permissions.base import BasePermission


class DRFPermissionAdapter:
    """Adapter that executes DFR permissions with DRF-like interface."""

    def __init__(self, permission: BasePermission) -> None:
        self.permission = permission

    async def has_permission(self, request: Any, view: Any | None = None) -> bool:
        return await self.permission.has_permission(request)

    async def has_object_permission(self, request: Any, view: Any | None, obj: Any) -> bool:
        return await self.permission.has_object_permission(request, obj)


__all__ = ["DRFPermissionAdapter"]
