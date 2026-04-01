"""Path conversion utilities for Django-style routes."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConvertedPath:
    template: str
    pattern: re.Pattern[str]


def django_path_to_regex(path: str) -> ConvertedPath:
    """Convert `<int:id>` style path to compiled regex.

    Example:
        `/users/<int:id>/` -> `^/users/(?P<id>\\d+)/$`
    """

    regex = re.escape(path)
    regex = regex.replace(re.escape("<int:"), "<int:").replace(re.escape(">"), ">")
    regex = re.sub(r"<int:([a-zA-Z_][a-zA-Z0-9_]*)>", r"(?P<\1>\\d+)", regex)
    regex = re.sub(r"<str:([a-zA-Z_][a-zA-Z0-9_]*)>", r"(?P<\1>[^/]+)", regex)
    regex = f"^{regex}$"
    return ConvertedPath(template=path, pattern=re.compile(regex))


__all__ = ["ConvertedPath", "django_path_to_regex"]
