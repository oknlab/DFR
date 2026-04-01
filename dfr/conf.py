"""Configuration objects for DFR."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DFRConfig:
    """Top-level runtime configuration for DFR.

    Example:
        >>> config = DFRConfig(django_settings_module="project.settings")
        >>> config.django_settings_module
        'project.settings'
    """

    django_settings_module: str
    debug: bool = False
    orm_executor_workers: int = 16
    route_prefix: str = ""
    openapi_enabled: bool = True
    extra: dict[str, str] = field(default_factory=dict)


__all__ = ["DFRConfig"]
