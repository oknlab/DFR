"""Public dependency injection APIs."""

from dfr.deps.auth import (
    DjangoAuthDependency,
    DjangoSessionAuthDependency,
    RequireAuthenticatedUser,
    current_user_dependency,
)
from dfr.deps.core import DependencyContainer, Depends, resolve_dependencies
from dfr.deps.db import transaction
from dfr.deps.pagination import PageParams, pagination_params

__all__ = [
    "DependencyContainer",
    "Depends",
    "PageParams",
    "DjangoAuthDependency",
    "DjangoSessionAuthDependency",
    "RequireAuthenticatedUser",
    "current_user_dependency",
    "pagination_params",
    "resolve_dependencies",
    "transaction",
]
