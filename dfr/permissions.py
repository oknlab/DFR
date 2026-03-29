"""Permission adapters and policy evaluation for DFR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from dfr.auth import AuthContext
from dfr.sync import run_sync

__all__ = [
    "AllowAny",
    "AsyncPermission",
    "BasePermission",
    "DFRRequestAdapter",
    "DjangoModelPermissions",
    "IsAdminUser",
    "IsAuthenticated",
    "PermissionDeniedError",
    "check_permissions",
    "check_permissions_async",
]


class PermissionDeniedError(RuntimeError):
    """Raised when one or more permission checks fail."""


@dataclass(slots=True)
class DFRRequestAdapter:
    """DRF-style request adapter over DFR/Starlette/Django request objects."""

    raw_request: Any

    @property
    def user(self) -> Any | None:
        state = getattr(self.raw_request, "state", None)
        auth_ctx = getattr(state, "_dfr_auth", None) if state is not None else None
        if isinstance(auth_ctx, AuthContext):
            return auth_ctx.user
        return getattr(self.raw_request, "user", None)

    @property
    def auth(self) -> Any | None:
        state = getattr(self.raw_request, "state", None)
        auth_ctx = getattr(state, "_dfr_auth", None) if state is not None else None
        if isinstance(auth_ctx, AuthContext):
            return auth_ctx.auth_token
        return getattr(self.raw_request, "auth", None)

    @property
    def data(self) -> Any:
        if hasattr(self.raw_request, "data"):
            return self.raw_request.data
        return getattr(self.raw_request, "_body", None)

    @property
    def query_params(self) -> dict[str, Any]:
        params = getattr(self.raw_request, "query_params", None)
        if params is not None:
            return dict(params)
        get_data = getattr(self.raw_request, "GET", None)
        if get_data is not None:
            return dict(get_data)
        return {}

    @property
    def method(self) -> str:
        return str(getattr(self.raw_request, "method", "GET")).upper()


class BasePermission:
    """Base class mirroring DRF permission interface."""

    def has_permission(self, request: DFRRequestAdapter, view: Any) -> bool:
        return True

    def has_object_permission(self, request: DFRRequestAdapter, view: Any, obj: Any) -> bool:
        return True


class AsyncPermission(Protocol):
    """Async permission protocol for async-native implementations."""

    async def has_permission(self, request: DFRRequestAdapter, view: Any) -> bool:
        ...

    async def has_object_permission(self, request: DFRRequestAdapter, view: Any, obj: Any) -> bool:
        ...


class AllowAny(BasePermission):
    """Permission class that always allows access."""


class IsAuthenticated(BasePermission):
    """Require authenticated user."""

    def has_permission(self, request: DFRRequestAdapter, view: Any) -> bool:
        user = request.user
        return bool(user is not None and getattr(user, "is_authenticated", False))


class IsAdminUser(BasePermission):
    """Require Django staff user."""

    def has_permission(self, request: DFRRequestAdapter, view: Any) -> bool:
        user = request.user
        return bool(user is not None and getattr(user, "is_staff", False))


class DjangoModelPermissions(BasePermission):
    """Map HTTP method to Django model permission codenames."""

    perms_map: dict[str, str] = {
        "GET": "view",
        "HEAD": "view",
        "OPTIONS": "view",
        "POST": "add",
        "PUT": "change",
        "PATCH": "change",
        "DELETE": "delete",
    }

    def has_permission(self, request: DFRRequestAdapter, view: Any) -> bool:
        user = request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return False

        queryset = getattr(view, "queryset", None)
        model = getattr(getattr(queryset, "model", None), "_meta", None)
        if model is None:
            return True

        action = self.perms_map.get(request.method, "view")
        app_label = model.app_label
        model_name = model.model_name
        codename = f"{app_label}.{action}_{model_name}"
        return bool(user.has_perm(codename))


def check_permissions(request: Any, view: Any, permission_classes: list[type[BasePermission] | BasePermission]) -> None:
    """Run synchronous permission checks and raise on failure."""

    adapted = DFRRequestAdapter(request)
    for perm in _instantiate_permissions(permission_classes):
        if isinstance(perm, BasePermission):
            if not perm.has_permission(adapted, view):
                raise PermissionDeniedError(
                    f"Permission '{perm.__class__.__name__}' denied access. Configure permission_classes or authenticate user."
                )
            continue
        raise PermissionDeniedError(
            f"Permission '{perm.__class__.__name__}' is async-only. Use check_permissions_async() in async request flow."
        )


async def check_permissions_async(request: Any, view: Any, permission_classes: list[type[Any] | Any]) -> None:
    """Run async-aware permission checks and raise on failure."""

    adapted = DFRRequestAdapter(request)
    for perm in _instantiate_permissions(permission_classes):
        if isinstance(perm, BasePermission):
            # FOOTGUN: sync permission checks may call ORM-backed user.has_perm and block the event loop.
            allowed = await run_sync(perm.has_permission, adapted, view, thread_sensitive=True)
        else:
            allowed = await perm.has_permission(adapted, view)

        if not allowed:
            raise PermissionDeniedError(
                f"Permission '{perm.__class__.__name__}' denied access. Configure permission_classes or authenticate user."
            )


def _instantiate_permissions(permission_classes: list[type[Any] | Any]) -> list[Any]:
    permissions: list[Any] = []
    for item in permission_classes:
        permissions.append(item() if isinstance(item, type) else item)
    return permissions
