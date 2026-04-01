import asyncio
import json

from dfr.app import DFR
from dfr.conf import DFRConfig
from dfr.routing import RouteRegistry, UnifiedDispatcher, include


def test_dispatch_async_route() -> None:
    app = DFR(DFRConfig(django_settings_module="project.settings"))

    @app.route("/health")
    async def health(_scope):
        return {"ok": True}

    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app({"type": "http", "path": "/health", "method": "GET"}, receive, send))

    assert messages[0]["status"] == 200
    assert json.loads(messages[1]["body"]) == {"ok": True}


def test_dispatch_sync_route() -> None:
    registry = RouteRegistry()

    def sync_handler(_scope):
        return {"mode": "sync"}

    registry.add("/sync", ["GET"], sync_handler)
    dispatcher = UnifiedDispatcher(registry)

    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(dispatcher({"type": "http", "path": "/sync", "method": "GET"}, receive, send))

    assert messages[0]["status"] == 200
    assert json.loads(messages[1]["body"]) == {"mode": "sync"}


def test_include_preserves_empty_registry() -> None:
    empty = RouteRegistry()
    assert include(empty) is empty


def test_dispatch_django_adapter_fallback() -> None:
    from dfr.routing import DjangoURLAdapter

    adapter = DjangoURLAdapter()

    def detail(_scope, id):
        return {"id": int(id)}

    adapter.add("/users/<int:id>/", detail)
    dispatcher = UnifiedDispatcher(RouteRegistry(), django_adapter=adapter)

    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(dispatcher({"type": "http", "path": "/users/7/", "method": "GET"}, receive, send))

    assert messages[0]["status"] == 200
    assert json.loads(messages[1]["body"]) == {"id": 7}


def test_dispatcher_route_ownership_cache() -> None:
    registry = RouteRegistry()

    def sync_handler(_scope):
        return {"cached": True}

    registry.add("/cached", ["GET"], sync_handler)
    dispatcher = UnifiedDispatcher(registry)

    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(dispatcher({"type": "http", "path": "/cached", "method": "GET"}, receive, send))
    assert dispatcher._route_ownership["/cached"] == "registry"
