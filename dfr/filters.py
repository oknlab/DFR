"""Queryset filter backends for DFR."""

from __future__ import annotations

from typing import Any, Protocol

from django.db.models import Q, QuerySet

from dfr.permissions import DFRRequestAdapter
from dfr.sync import run_sync

__all__ = [
    "AsyncFilterBackend",
    "BaseFilterBackend",
    "DjangoFilterBackend",
    "FilterError",
    "OrderingFilter",
    "SearchFilter",
    "apply_filters",
    "apply_filters_async",
]


class FilterError(RuntimeError):
    """Raised when filtering configuration or execution fails."""


class BaseFilterBackend:
    """DRF-style filter backend base class."""

    def filter_queryset(self, request: DFRRequestAdapter, queryset: QuerySet[Any], view: Any) -> QuerySet[Any]:
        return queryset


class AsyncFilterBackend(Protocol):
    """Async-native filter backend protocol."""

    async def filter_queryset(self, request: DFRRequestAdapter, queryset: QuerySet[Any], view: Any) -> QuerySet[Any]:
        ...


class DjangoFilterBackend(BaseFilterBackend):
    """Simple field-value filtering or django-filter delegation."""

    def __init__(self, *, fields: list[str] | None = None, filterset_class: Any | None = None) -> None:
        self.fields = fields
        self.filterset_class = filterset_class

    def filter_queryset(self, request: DFRRequestAdapter, queryset: QuerySet[Any], view: Any) -> QuerySet[Any]:
        params = request.query_params
        if self.filterset_class is not None:
            try:
                import django_filters
            except Exception as exc:
                raise FilterError(
                    "django-filter is required when filterset_class is provided. Install 'django-filter' or remove filterset_class."
                ) from exc

            filterset = self.filterset_class(data=params, queryset=queryset, request=request.raw_request)
            if not filterset.is_valid():
                raise FilterError(f"Invalid filter params: {filterset.errors}")
            return filterset.qs

        if not self.fields:
            return queryset

        model = queryset.model
        filters: dict[str, Any] = {}
        for field_name in self.fields:
            if field_name not in params:
                continue
            raw_value = params[field_name]
            model_field = model._meta.get_field(field_name)
            filters[field_name] = _coerce_value(model_field, raw_value)

        if not filters:
            return queryset
        return queryset.filter(**filters)


class SearchFilter(BaseFilterBackend):
    """Apply icontains OR search across configured fields."""

    def __init__(self, *, search_fields: list[str]) -> None:
        self.search_fields = search_fields

    def filter_queryset(self, request: DFRRequestAdapter, queryset: QuerySet[Any], view: Any) -> QuerySet[Any]:
        term = request.query_params.get("search")
        if not term:
            return queryset
        query = Q()
        for field in self.search_fields:
            query |= Q(**{f"{field}__icontains": term})
        return queryset.filter(query)


class OrderingFilter(BaseFilterBackend):
    """Apply validated ordering expressions from query parameters."""

    def __init__(self, *, ordering_fields: list[str] | None = None, default_ordering: str | None = None) -> None:
        self.ordering_fields = ordering_fields
        self.default_ordering = default_ordering

    def filter_queryset(self, request: DFRRequestAdapter, queryset: QuerySet[Any], view: Any) -> QuerySet[Any]:
        raw = request.query_params.get("ordering")
        if not raw:
            if self.default_ordering:
                return queryset.order_by(self.default_ordering)
            return queryset

        fields = [value.strip() for value in str(raw).split(",") if value.strip()]
        if self.ordering_fields is not None:
            allowed = set(self.ordering_fields)
            for item in fields:
                candidate = item[1:] if item.startswith("-") else item
                if candidate not in allowed:
                    raise FilterError(f"Ordering field '{candidate}' is not allowed. Configure ordering_fields to permit it.")
        return queryset.order_by(*fields)


def apply_filters(
    request: Any,
    queryset: QuerySet[Any],
    view: Any,
    filter_backends: list[type[Any] | Any],
) -> QuerySet[Any]:
    """Apply filter backends sequentially in sync flow."""

    adapted = DFRRequestAdapter(request)
    current = queryset
    for backend in _instantiate_backends(filter_backends):
        if _is_async_backend(backend):
            raise FilterError(
                f"Filter backend '{backend.__class__.__name__}' is async-only. Use apply_filters_async() in async flow."
            )
        current = backend.filter_queryset(adapted, current, view)
    return current


async def apply_filters_async(
    request: Any,
    queryset: QuerySet[Any],
    view: Any,
    filter_backends: list[type[Any] | Any],
) -> QuerySet[Any]:
    """Apply filter backends sequentially in async flow."""

    adapted = DFRRequestAdapter(request)
    current = queryset
    for backend in _instantiate_backends(filter_backends):
        if _is_async_backend(backend):
            current = await backend.filter_queryset(adapted, current, view)
        else:
            # FOOTGUN: queryset filtering is sync ORM work; run inside sync boundary when in async request flow.
            current = await run_sync(backend.filter_queryset, adapted, current, view, thread_sensitive=True)
    return current


def _instantiate_backends(filter_backends: list[type[Any] | Any]) -> list[Any]:
    out: list[Any] = []
    for backend in filter_backends:
        out.append(backend() if isinstance(backend, type) else backend)
    return out


def _is_async_backend(backend: Any) -> bool:
    fn = getattr(backend, "filter_queryset", None)
    return callable(fn) and getattr(fn, "__code__", None) is not None and fn.__code__.co_flags & 0x80 != 0


def _coerce_value(model_field: Any, raw_value: Any) -> Any:
    internal = getattr(model_field, "get_internal_type", lambda: "")()
    value = str(raw_value)
    if internal in {"IntegerField", "SmallIntegerField", "BigIntegerField", "AutoField", "BigAutoField"}:
        try:
            return int(value)
        except ValueError:
            return raw_value
    if internal in {"FloatField", "DecimalField"}:
        try:
            return float(value)
        except ValueError:
            return raw_value
    if internal in {"BooleanField", "NullBooleanField"}:
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return raw_value
