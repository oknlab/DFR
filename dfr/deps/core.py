"""Dependency injection primitives inspired by FastAPI's Depends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from dfr.exceptions import DependencyResolutionError


@dataclass(frozen=True, slots=True)
class Depends:
    """Declare a dependency callable with optional keyword arguments.

    Example:
        >>> dep = Depends(lambda: 1)
        >>> dep.dependency()
        1
    """

    dependency: Callable[..., Any]
    kwargs: dict[str, Any] = field(default_factory=dict)
    use_cache: bool = True

    def __hash__(self) -> int:
        return hash((self.dependency, tuple(sorted(self.kwargs.items()))))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Depends):
            return False
        return (
            self.dependency is other.dependency
            and tuple(sorted(self.kwargs.items())) == tuple(sorted(other.kwargs.items()))
        )


class DependencyContainer:
    """Resolve and cache dependency results during a single request lifecycle."""

    def __init__(self) -> None:
        self._cache: dict[Depends, Any] = {}

    async def resolve(self, dep: Depends) -> Any:
        """Resolve one dependency and return its value."""
        if dep.use_cache and dep in self._cache:
            return self._cache[dep]

        try:
            value = dep.dependency(**dep.kwargs)
            if hasattr(value, "__await__"):
                value = await value
        except Exception as exc:  # noqa: BLE001
            raise DependencyResolutionError(
                f"Failed resolving dependency {dep.dependency.__name__!r}: {exc}"
            ) from exc

        if dep.use_cache:
            self._cache[dep] = value
        return value


async def resolve_dependencies(*deps: Depends) -> tuple[Any, ...]:
    """Resolve dependencies in order and return their values as a tuple."""
    container = DependencyContainer()
    results: list[Any] = []
    for dep in deps:
        results.append(await container.resolve(dep))
    return tuple(results)


__all__ = ["DependencyContainer", "Depends", "resolve_dependencies"]
