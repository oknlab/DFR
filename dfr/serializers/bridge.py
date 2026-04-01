"""Pydantic v2 bridge for Django-like model objects."""

from __future__ import annotations

import importlib
import importlib.util
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


_HAS_PYDANTIC = importlib.util.find_spec("pydantic") is not None

if _HAS_PYDANTIC:
    pydantic = importlib.import_module("pydantic")
    BaseModel = pydantic.BaseModel
    ConfigDict = pydantic.ConfigDict

    class DFRSchema(BaseModel):
        """Pydantic-backed schema that can persist to configured Django-like models."""

        model_config = ConfigDict(arbitrary_types_allowed=True)
        dfr_model_config: DFRModelConfig = DFRModelConfig()

        @classmethod
        def get_django_model(cls) -> type[Any]:
            model = cls.dfr_model_config.django_model
            if model is None:
                raise ConfigurationError(
                    f"{cls.__name__} requires `dfr_model_config = DFRModelConfig(django_model=...)`."
                )
            return model

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
            for field_name in cls.model_fields:
                if hasattr(model, field_name):
                    data[field_name] = getattr(model, field_name)
            return cls.model_validate(data)

else:

    class DFRSchema:
        """Placeholder when pydantic is unavailable."""

        dfr_model_config: DFRModelConfig = DFRModelConfig()

        def __init__(self, **kwargs: Any) -> None:
            raise RuntimeError(
                "Pydantic v2 is required for DFRSchema. Install with `pip install pydantic>=2.8,<3`."
            )


__all__ = ["DFRModelConfig", "DFRSchema", "_HAS_PYDANTIC"]
