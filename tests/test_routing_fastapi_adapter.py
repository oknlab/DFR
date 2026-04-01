import asyncio
import json

from dfr.app import DFR
from dfr.conf import DFRConfig
from dfr.routing import FastAPIRouterAdapter, RouteRegistry, UnifiedDispatcher


class FakeRoute:
    def __init__(self, path, methods, endpoint):
        self.path = path
        self.methods = methods
        self.endpoint = endpoint


class FakeRouter:
    def __init__(self, routes):
        self.routes = routes


def test_fastapi_adapter_resolve() -> None:
    adapter = FastAPIRouterAdapter()

    def endpoint(_scope):
        return {"ok": True}

    adapter.attach_router(FakeRouter([FakeRoute("/fa", {"GET"}, endpoint)]))
    resolved = adapter.resolve("/fa", "GET")
    assert resolved is not None


def test_dispatch_fastapi_adapter_fallback() -> None:
    def endpoint(_scope):
        return {"source": "fastapi"}

    adapter = FastAPIRouterAdapter()
    adapter.attach_router(FakeRouter([FakeRoute("/fa", {"GET"}, endpoint)]))
    dispatcher = UnifiedDispatcher(RouteRegistry(), fastapi_adapter=adapter)

    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(dispatcher({"type": "http", "path": "/fa", "method": "GET"}, receive, send))
    assert json.loads(messages[1]["body"]) == {"source": "fastapi"}


def test_app_include_fastapi_router() -> None:
    app = DFR(DFRConfig(django_settings_module="project.settings"))

    def endpoint(_scope):
        return {"ok": True}

    app.include_fastapi_router(FakeRouter([FakeRoute("/fa", {"GET"}, endpoint)]))
    assert app.fastapi_adapter.resolve("/fa", "GET") is not None
