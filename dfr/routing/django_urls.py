"""Lightweight Django URL resolver adapter for DFR routing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dfr.routing.converters import ConvertedPath, django_path_to_regex


@dataclass(slots=True)
class DjangoRoute:
    path: str
    endpoint: Callable[..., Any]
    converted: ConvertedPath


class DjangoURLAdapter:
    """Stores Django-like path definitions and resolves by regex match."""

    def __init__(self) -> None:
        self._routes: list[DjangoRoute] = []

    def add(self, path: str, endpoint: Callable[..., Any]) -> None:
        self._routes.append(DjangoRoute(path=path, endpoint=endpoint, converted=django_path_to_regex(path)))

    def resolve(self, request_path: str) -> tuple[Callable[..., Any], dict[str, str]] | None:
        for route in self._routes:
            match = route.converted.pattern.match(request_path)
            if match:
                return route.endpoint, match.groupdict()
        return None


__all__ = ["DjangoRoute", "DjangoURLAdapter"]
