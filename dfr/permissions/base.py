"""Permission primitives compatible with async request handling."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePermission(ABC):
    """Base permission contract."""

    @abstractmethod
    async def has_permission(self, request: Any) -> bool:
        """Return whether the request is globally allowed."""

    async def has_object_permission(self, request: Any, obj: Any) -> bool:
        """Return whether the request can access a concrete object."""
        return await self.has_permission(request)


class AllowAny(BasePermission):
    """Permission class that allows all requests."""

    async def has_permission(self, request: Any) -> bool:
        return True


__all__ = ["AllowAny", "BasePermission"]
