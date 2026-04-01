"""Django URLResolver adapter for DFR routing."""

from __future__ import annotations

import importlib
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
    """Resolve routes from either local patterns or Django URLResolver."""

    def __init__(self) -> None:
        self._routes: list[DjangoRoute] = []
        self._django_resolver: Any | None = None

    def add(self, path: str, endpoint: Callable[..., Any]) -> None:
        self._routes.append(DjangoRoute(path=path, endpoint=endpoint, converted=django_path_to_regex(path)))

    def load_urlconf(self, urlconf: str) -> None:
        """Load a real Django URL resolver from a URLConf module path."""
        django_urls = importlib.import_module("django.urls")
        self._django_resolver = django_urls.get_resolver(urlconf)

    def set_resolver(self, resolver: Any) -> None:
        """Inject resolver for tests or custom integrations."""
        self._django_resolver = resolver

    def resolve(self, request_path: str) -> tuple[Callable[..., Any], dict[str, Any]] | None:
        if self._django_resolver is not None:
            match = self._resolve_django(request_path)
            if match is not None:
                return match

        for route in self._routes:
            match = route.converted.pattern.match(request_path)
            if match:
                return route.endpoint, match.groupdict()
        return None

    def _resolve_django(self, request_path: str) -> tuple[Callable[..., Any], dict[str, Any]] | None:
        normalized = request_path.lstrip("/")
        try:
            match = self._django_resolver.resolve(normalized)
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ in {"Resolver404", "Http404"}:
                return None
            raise

        kwargs = dict(getattr(match, "kwargs", {}))
        args = tuple(getattr(match, "args", ()))
        if args and "args" not in kwargs:
            kwargs["args"] = args
        return match.func, kwargs


__all__ = ["DjangoRoute", "DjangoURLAdapter"]
