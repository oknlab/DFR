"""Pydantic v2 powered model schemas for DFR.

This module provides a DRF-style ``ModelSchema`` interface backed by
Django model metadata and Pydantic v2 validation.

Example:
    from dfr.serializers import ModelSchema

    class UserSchema(ModelSchema):
        class Meta:
            model = User
            fields = ["id", "email", "is_active"]
            read_only = ["id"]

    payload = UserSchema.model_validate({"email": "a@example.com", "is_active": True})
    user = await UserSchema.save_async(payload)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from types import NoneType
from typing import Any, ClassVar, Mapping, MutableMapping, TypeAlias, get_args, get_origin
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, ValidationError

from dfr.sync import run_sync

__all__ = [
    "DFRErrorDetail",
    "DFRValidationError",
    "ModelSchema",
    "normalize_validation_error",
]

ModelType: TypeAlias = type[models.Model]

_CONSTRAINT_RE = re.compile(r"(?P<constraint>[A-Za-z0-9_]+)")
_MODEL_TO_SCHEMA: dict[ModelType, type["ModelSchema"]] = {}


@dataclass(slots=True, frozen=True)
class DFRErrorDetail:
    """Normalized validation error detail.

    Attributes:
        loc: Error location path.
        msg: Human-readable message.
        type: Error type string.
        code: Stable code used for API clients.
    """

    loc: tuple[str | int, ...]
    msg: str
    type: str
    code: str


class DFRValidationError(ValueError):
    """Unified validation exception used by DFR serializers."""

    def __init__(self, errors: list[DFRErrorDetail]) -> None:
        super().__init__("Validation failed. Inspect .errors for normalized detail.")
        self._errors = errors

    @property
    def errors(self) -> list[DFRErrorDetail]:
        """Return normalized validation details."""

        return self._errors


class ModelSchema(BaseModel):
    """DRF-style schema base class powered by Pydantic v2.

    Subclasses define ``Meta`` to map Django models to typed validation models.

    Example:
        class ArticleSchema(ModelSchema):
            class Meta:
                model = Article
                fields = ["id", "title", "author"]
                read_only = ["id"]
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, arbitrary_types_allowed=True)

    class Meta:
        """Default meta options for model-backed schema subclasses."""

        model: ModelType | None = None
        fields: list[str] | str = "__all__"
        exclude: list[str] = []
        read_only: list[str] = []
        write_only: list[str] = []
        id_only_relations: list[str] = []

    _meta_model: ClassVar[ModelType | None] = None
    _meta_fields: ClassVar[tuple[str, ...]] = ()
    _read_only: ClassVar[frozenset[str]] = frozenset()
    _write_only: ClassVar[frozenset[str]] = frozenset()
    _id_only_relations: ClassVar[frozenset[str]] = frozenset()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is ModelSchema:
            return

        meta = getattr(cls, "Meta", None)
        if meta is None:
            raise TypeError(f"{cls.__name__} must declare an inner Meta class with a Django model.")

        model = getattr(meta, "model", None)
        if model is None:
            raise TypeError(f"{cls.__name__}.Meta.model is required and must be a Django model class.")

        cls._meta_model = model
        cls._meta_fields = _resolve_field_names(model, getattr(meta, "fields", "__all__"), getattr(meta, "exclude", []))
        cls._read_only = frozenset(getattr(meta, "read_only", []))
        cls._write_only = frozenset(getattr(meta, "write_only", []))
        cls._id_only_relations = frozenset(getattr(meta, "id_only_relations", []))

        annotations = dict(getattr(cls, "__annotations__", {}))
        for field_name in cls._meta_fields:
            if field_name in annotations:
                continue
            django_field = _lookup_model_field(model, field_name)
            if django_field is None:
                continue
            annotations[field_name] = _compile_python_type(cls, django_field)
            default_value = _compile_default(field_name, django_field, cls._read_only, cls._write_only)
            if default_value is not _MISSING and field_name not in cls.__dict__:
                setattr(cls, field_name, default_value)

        cls.__annotations__ = annotations
        cls.model_rebuild(force=True)
        _MODEL_TO_SCHEMA[model] = cls

    @classmethod
    async def save_async(
        cls,
        validated_data: Mapping[str, Any] | "ModelSchema",
        *,
        instance: models.Model | None = None,
    ) -> models.Model:
        """Persist validated payload into Django ORM.

        Args:
            validated_data: Mapping or validated ModelSchema instance.
            instance: Existing instance for update operations.

        Returns:
            Saved Django model instance.

        Raises:
            DFRValidationError: On pydantic/django/integrity failures.
        """

        if cls._meta_model is None:
            raise TypeError(f"{cls.__name__} is not bound to a Django model. Set Meta.model.")

        payload = _coerce_payload(validated_data)

        def _write_unit() -> models.Model:
            try:
                return _persist_model(cls, payload, instance)
            except (DjangoValidationError, IntegrityError) as exc:
                raise DFRValidationError(normalize_validation_error(exc)) from exc

        try:
            # FOOTGUN: per-field run_sync boundaries can deadlock and thrash threads; use one coarse write block.
            return await run_sync(_write_unit, thread_sensitive=True)
        except ValidationError as exc:
            raise DFRValidationError(normalize_validation_error(exc)) from exc


def normalize_validation_error(error: Exception) -> list[DFRErrorDetail]:
    """Normalize Pydantic/Django/DB errors into DFR error details."""

    if isinstance(error, ValidationError):
        details: list[DFRErrorDetail] = []
        for item in error.errors():
            location = tuple(item.get("loc", ("non_field_errors",)))
            details.append(
                DFRErrorDetail(
                    loc=location,
                    msg=str(item.get("msg", "Invalid value.")),
                    type=str(item.get("type", "validation_error")),
                    code=str(item.get("type", "invalid")),
                )
            )
        return details

    if isinstance(error, DjangoValidationError):
        if hasattr(error, "error_dict"):
            details = []
            for field_name, error_list in error.error_dict.items():
                for entry in error_list:
                    details.append(
                        DFRErrorDetail(
                            loc=(field_name,),
                            msg=str(entry.message),
                            type="django_validation_error",
                            code=str(entry.code or "invalid"),
                        )
                    )
            return details

        return [
            DFRErrorDetail(
                loc=("non_field_errors",),
                msg=str(message),
                type="django_validation_error",
                code="invalid",
            )
            for message in error.messages
        ]

    if isinstance(error, IntegrityError):
        text = str(error)
        constraint = _extract_constraint_name(text)
        loc: tuple[str | int, ...] = (constraint,) if constraint is not None else ("non_field_errors",)
        return [
            DFRErrorDetail(
                loc=loc,
                msg=text,
                type="integrity_error",
                code="integrity_error",
            )
        ]

    return [
        DFRErrorDetail(
            loc=("non_field_errors",),
            msg=str(error),
            type="unknown_error",
            code="unknown",
        )
    ]


class _MissingType:
    pass


_MISSING = _MissingType()


def _resolve_field_names(model: ModelType, fields: list[str] | str, exclude: list[str]) -> tuple[str, ...]:
    excluded = set(exclude)
    if fields == "__all__":
        names: list[str] = []
        for field in model._meta.get_fields():
            if getattr(field, "auto_created", False) and not field.concrete:
                continue
            name = getattr(field, "name", "")
            if name and name not in excluded:
                names.append(name)
        return tuple(names)

    names = [name for name in fields if name not in excluded]
    return tuple(names)


def _lookup_model_field(model: ModelType, field_name: str) -> models.Field[Any, Any] | None:
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return None
    return field


def _compile_python_type(schema_cls: type[ModelSchema], field: models.Field[Any, Any]) -> Any:
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        if field.name in schema_cls._id_only_relations:
            base: Any = int
        else:
            related_model = field.related_model
            related_schema = _MODEL_TO_SCHEMA.get(related_model)
            base = related_schema if related_schema is not None else int
        return _apply_optional(base, field)

    if isinstance(field, models.ManyToManyField):
        related_schema = _MODEL_TO_SCHEMA.get(field.related_model)
        item_type: Any = int if field.name in schema_cls._id_only_relations else (related_schema or int)
        return list[item_type]

    if getattr(field, "one_to_many", False) and getattr(field, "auto_created", False):
        related_model = getattr(field, "related_model", None)
        related_schema = _MODEL_TO_SCHEMA.get(related_model)
        item_type = related_schema or int
        return list[item_type]

    mapping: list[tuple[type[Any], Any]] = [
        (models.EmailField, EmailStr),
        (models.URLField, AnyHttpUrl),
        (models.SlugField, str),
        (models.TextField, str),
        (models.CharField, str),
        (models.IntegerField, int),
        (models.SmallIntegerField, int),
        (models.BigIntegerField, int),
        (models.AutoField, int),
        (models.BigAutoField, int),
        (models.FloatField, float),
        (models.DecimalField, Decimal),
        (models.BooleanField, bool),
        (models.DateTimeField, datetime),
        (models.DateField, date),
        (models.TimeField, time),
        (models.UUIDField, UUID),
        (models.JSONField, dict[str, Any]),
        (models.FileField, str),
        (models.ImageField, str),
    ]

    resolved: Any = str
    for klass, python_type in mapping:
        if isinstance(field, klass):
            resolved = python_type
            break

    return _apply_optional(resolved, field)


def _apply_optional(base: Any, field: models.Field[Any, Any]) -> Any:
    if getattr(field, "null", False):
        return base | NoneType
    return base


def _compile_default(
    field_name: str,
    field: models.Field[Any, Any],
    read_only: frozenset[str],
    write_only: frozenset[str],
) -> Any:
    if field_name in read_only or isinstance(field, (models.AutoField, models.BigAutoField)):
        return Field(default=None, json_schema_extra={"readOnly": True})

    if field_name in write_only:
        if field.has_default():
            default = field.get_default()
        elif getattr(field, "null", False):
            default = None
        elif isinstance(field, (models.CharField, models.TextField)) and getattr(field, "blank", False):
            default = ""
        else:
            default = ...
        return Field(default=default, exclude=True, json_schema_extra={"writeOnly": True})

    if field.has_default():
        return field.get_default()
    if getattr(field, "null", False):
        return None
    if isinstance(field, (models.CharField, models.TextField)) and getattr(field, "blank", False):
        return ""
    return _MISSING


def _coerce_payload(validated_data: Mapping[str, Any] | ModelSchema) -> dict[str, Any]:
    if isinstance(validated_data, ModelSchema):
        return dict(validated_data.model_dump(exclude_unset=True))
    return dict(validated_data)


def _persist_model(schema_cls: type[ModelSchema], payload: MutableMapping[str, Any], instance: models.Model | None) -> models.Model:
    model = schema_cls._meta_model
    if model is None:
        raise TypeError(f"{schema_cls.__name__} has no Meta.model configured.")

    simple_values: dict[str, Any] = {}
    relation_values: dict[str, Any] = {}

    for key, value in payload.items():
        field = _lookup_model_field(model, key)
        if field is None:
            continue
        if isinstance(field, models.ManyToManyField):
            relation_values[key] = value
            continue
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            simple_values[key] = _resolve_foreign_key_value(field, value)
            continue
        simple_values[key] = value

    if instance is None:
        obj = model.objects.create(**simple_values)
    else:
        obj = instance
        for name, value in simple_values.items():
            setattr(obj, name, value)
        obj.save()

    for field_name, value in relation_values.items():
        manager = getattr(obj, field_name)
        ids = _resolve_many_relation_values(model, field_name, value)
        manager.set(ids)

    obj.full_clean()
    obj.save()
    return obj


def _resolve_foreign_key_value(field: models.Field[Any, Any], value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        data = value.model_dump(exclude_unset=True)
        return data.get("id")
    if isinstance(value, Mapping):
        if "id" in value:
            return value["id"]
        related_model = getattr(field, "related_model", None)
        if related_model is not None:
            nested = related_model.objects.create(**dict(value))
            return nested.pk
    return value


def _resolve_many_relation_values(model: ModelType, field_name: str, value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DjangoValidationError({field_name: "Expected a list for many-to-many relation values."})

    output: list[Any] = []
    for item in value:
        if isinstance(item, BaseModel):
            data = item.model_dump(exclude_unset=True)
            if "id" not in data:
                raise DjangoValidationError({field_name: "Nested relation requires 'id' for many-to-many assignment."})
            output.append(data["id"])
            continue
        if isinstance(item, Mapping):
            if "id" in item:
                output.append(item["id"])
                continue
            relation_field = model._meta.get_field(field_name)
            related_model = getattr(relation_field, "related_model", None)
            if related_model is None:
                raise DjangoValidationError({field_name: "Unable to resolve related model for nested many-to-many payload."})
            nested = related_model.objects.create(**dict(item))
            output.append(nested.pk)
            continue
        output.append(item)
    return output


def _extract_constraint_name(message: str) -> str | None:
    match = _CONSTRAINT_RE.search(message)
    if match is None:
        return None
    return match.group("constraint")
