"""DFR exception hierarchy with actionable messages."""

from __future__ import annotations


class DFRException(Exception):
    """Base exception for all DFR errors."""


class ConfigurationError(DFRException):
    """Raised when DFR is misconfigured."""


class RoutingError(DFRException):
    """Raised for route registration and dispatch failures."""


class SerializationError(DFRException):
    """Raised for schema/model conversion issues."""


class DependencyResolutionError(DFRException):
    """Raised when dependency resolution fails."""


class MiddlewareError(DFRException):
    """Raised when middleware adaptation or execution fails."""


__all__ = [
    "ConfigurationError",
    "DFRException",
    "DependencyResolutionError",
    "MiddlewareError",
    "RoutingError",
    "SerializationError",
]
