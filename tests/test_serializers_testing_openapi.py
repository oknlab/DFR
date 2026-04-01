import pytest
import asyncio
from dataclasses import dataclass

from dfr.openapi import DFRSchemaGenerator
from dfr.serializers import DFRModelConfig, DFRSchema
from dfr.serializers.bridge import _HAS_PYDANTIC
from dfr.testing import create_test_client


@dataclass
class UserModel:
    username: str

    def save(self, **kwargs):
        return None


class UserSchema(DFRSchema):
    username: str
    dfr_model_config = DFRModelConfig(django_model=UserModel)


@pytest.mark.skipif(not _HAS_PYDANTIC, reason="pydantic not installed in runtime")
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


from dfr.app import DFR
from dfr.conf import DFRConfig


def test_openapi_from_app_registry() -> None:
    app = DFR(DFRConfig(django_settings_module="project.settings"))

    @app.route("/items", methods=["GET", "POST"], dependencies=["auth", "db"])
    async def items(_scope):
        """List items"""
        return {"ok": True}

    schema = app.openapi_schema(title="DFR", version="1.0.0")
    assert "/items" in schema["paths"]
    assert "get" in schema["paths"]["/items"]
    assert "post" in schema["paths"]["/items"]
    assert schema["paths"]["/items"]["get"]["x-dfr-dependencies"] == ["auth", "db"]
    assert schema["paths"]["/items"]["get"]["operationId"] == "items_get"
    assert schema["paths"]["/items"]["get"]["summary"] == "List items"
