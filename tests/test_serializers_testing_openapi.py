import asyncio
from dataclasses import dataclass

from dfr.openapi import DFRSchemaGenerator
from dfr.serializers import DFRModelConfig, DFRSchema
from dfr.testing import create_test_client


@dataclass
class UserModel:
    username: str

    def save(self, **kwargs):
        return None


class UserSchema(DFRSchema):
    username: str
    dfr_model_config = DFRModelConfig(django_model=UserModel)


def test_schema_can_create_model_instance() -> None:
    user = UserSchema(username="alice")
    instance = asyncio.run(user.asave())
    assert instance.username == "alice"


def test_openapi_schema_generator() -> None:
    schema = DFRSchemaGenerator().generate(title="DFR", version="0.1.0")
    assert schema["openapi"] == "3.1.0"


def test_testing_fixture_client() -> None:
    client = create_test_client()
    assert client is not None
