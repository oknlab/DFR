"""Schema bridge for Django-like model objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from dfr.async_ import sync_to_async
from dfr.exceptions import ConfigurationError, SerializationError


class SupportsSave(Protocol):
    """Protocol for model-like objects with `save()` method."""

    def save(self, **kwargs: Any) -> None: ...


@dataclass(slots=True)
class DFRModelConfig:
    """Configuration metadata for schema/model integration."""

    django_model: type[Any] | None = None
    write_exclude: set[str] = field(default_factory=set)
    field_aliases: dict[str, str] = field(default_factory=dict)


class DFRSchema:
    """Minimal typed schema base independent of external validators.

    Subclasses should define `__annotations__` and can be instantiated with keyword
    arguments matching those field names.
    """

    dfr_model_config: DFRModelConfig = DFRModelConfig()

    def __init__(self, **kwargs: Any) -> None:
        for field_name in self.__class__.__annotations__:
            if field_name in kwargs:
                setattr(self, field_name, kwargs[field_name])

    @classmethod
    def get_django_model(cls) -> type[Any]:
        model = cls.dfr_model_config.django_model
        if model is None:
            raise ConfigurationError(
                f"{cls.__name__} requires `dfr_model_config = DFRModelConfig(django_model=...)`."
            )
        return model

    def model_dump(self, *, exclude_unset: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field_name in self.__class__.__annotations__:
            if hasattr(self, field_name):
                data[field_name] = getattr(self, field_name)
            elif not exclude_unset:
                data[field_name] = None
        return data

    def _to_model_kwargs(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_unset=True)
        kwargs: dict[str, Any] = {}
        for key, value in payload.items():
            if key in self.dfr_model_config.write_exclude:
                continue
            model_key = self.dfr_model_config.field_aliases.get(key, key)
            kwargs[model_key] = value
        return kwargs

    async def asave(self, **kwargs: Any) -> Any:
        """Instantiate configured model from schema data and save it."""
        model_cls = self.get_django_model()
        try:
            instance: SupportsSave = model_cls(**self._to_model_kwargs())
        except Exception as exc:  # noqa: BLE001
            raise SerializationError(f"Could not instantiate model {model_cls!r}: {exc}") from exc

        await sync_to_async(instance.save, **kwargs)
        return instance

    @classmethod
    def from_model(cls, model: Any) -> "DFRSchema":
        data = {}
        for field_name in cls.__annotations__:
            if hasattr(model, field_name):
                data[field_name] = getattr(model, field_name)
        return cls(**data)


__all__ = ["DFRModelConfig", "DFRSchema"]
