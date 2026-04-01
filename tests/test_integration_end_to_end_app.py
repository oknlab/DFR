import asyncio
import json

from dfr.app import DFR
from dfr.conf import DFRConfig
from dfr.routing import DjangoURLAdapter


class FakeRoute:
    def __init__(self, path, methods, endpoint):
        self.path = path
        self.methods = methods
        self.endpoint = endpoint


class FakeRouter:
    def __init__(self, routes):
        self.routes = routes


async def _invoke(app, path: str, method: str = "GET") -> list[dict]:
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "path": path, "method": method}, receive, send)
    return messages


def test_end_to_end_registry_fastapi_django_fallbacks() -> None:
    app = DFR(DFRConfig(django_settings_module="project.settings"))

    @app.route("/registry")
    async def registry_endpoint(_scope):
        return {"source": "registry"}

    def fastapi_endpoint(_scope):
        return {"source": "fastapi"}

    app.include_fastapi_router(FakeRouter([FakeRoute("/fa", {"GET"}, fastapi_endpoint)]))

    django_adapter = DjangoURLAdapter()

    def django_endpoint(_scope, slug):
        return {"source": "django", "slug": slug}

    django_adapter.add("/dj/<str:slug>/", django_endpoint)
    app.dispatcher.django_adapter = django_adapter

    reg = asyncio.run(_invoke(app, "/registry"))
    fa = asyncio.run(_invoke(app, "/fa"))
    dj = asyncio.run(_invoke(app, "/dj/abc/"))

    assert json.loads(reg[1]["body"]) == {"source": "registry"}
    assert json.loads(fa[1]["body"]) == {"source": "fastapi"}
    assert json.loads(dj[1]["body"]) == {"source": "django", "slug": "abc"}
