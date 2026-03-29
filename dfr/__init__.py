"""Public package exports for DFR."""

from __future__ import annotations

from dfr.app import DFRApp
from dfr.auth import CurrentUser
from dfr.deps import Depends
from dfr.openapi import generate_openapi
from dfr.routing import include_django_urls, include_router, route
from dfr.serializers import ModelSchema

__all__ = [
    "CurrentUser",
    "DFRApp",
    "Depends",
    "ModelSchema",
    "generate_openapi",
    "include_django_urls",
    "include_router",
    "route",
]

__version__ = "0.1.0"
