"""Testing helpers and pytest fixtures for DFR.

Example:
    from dfr.testing import create_test_clients

    clients = create_test_clients(app)
    response = clients.sync.get("/health")
"""

from __future__ import annotations

from typing import Any, NamedTuple

import pytest

try:  # optional runtime dependency for async test client
    import httpx
except Exception:  # pragma: no cover - environment-dependent dependency
    httpx = None  # type: ignore[assignment]

try:  # optional runtime dependency for sync Django test client
    from django.test import Client as DjangoClient
except Exception:  # pragma: no cover - environment-dependent dependency
    DjangoClient = None  # type: ignore[assignment]

from dfr.app import DFRApp
from dfr.auth import _BACKENDS
from dfr.deps import get_container
from dfr.middleware import RequestContext
from dfr.routing import get_registry

__all__ = [
    "DFRTestClient",
    "TestClients",
    "create_test_clients",
    "dfr_app",
    "dfr_async_client",
    "dfr_client",
    "reset_app_state",
    "reset_request_context",
]


class TestClients(NamedTuple):
    """Paired sync and async clients for DFR tests."""

    sync: "DFRTestClient"
    async_client: Any


class DFRTestClient:
    """Facade over Django test client for sync endpoint testing."""

    def __init__(self, app: Any) -> None:
        self._app = app
        if DjangoClient is None:
            raise RuntimeError("Django test client is unavailable. Install Django to use DFRTestClient.")
        self._client = DjangoClient()

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._client.get(path, **kwargs)

    def post(self, path: str, data: Any | None = None, **kwargs: Any) -> Any:
        return self._client.post(path, data=data, **kwargs)

    def put(self, path: str, data: Any | None = None, **kwargs: Any) -> Any:
        return self._client.put(path, data=data, **kwargs)

    def patch(self, path: str, data: Any | None = None, **kwargs: Any) -> Any:
        return self._client.patch(path, data=data, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._client.delete(path, **kwargs)

    def options(self, path: str, **kwargs: Any) -> Any:
        return self._client.options(path, **kwargs)

    def head(self, path: str, **kwargs: Any) -> Any:
        return self._client.head(path, **kwargs)


def create_test_clients(app: Any) -> TestClients:
    """Create paired sync/async clients for DFR test runs."""

    sync_client = DFRTestClient(app)
    if httpx is None:
        raise RuntimeError("httpx is unavailable. Install httpx to create async test clients.")
    async_client = httpx.AsyncClient(app=app, base_url="http://testserver")
    return TestClients(sync=sync_client, async_client=async_client)


def reset_app_state(app: Any) -> None:
    """Reset global singleton state for deterministic tests."""

    _ = app
    registry = get_registry()
    registry._entries.clear()  # noqa: SLF001 - intentional internal cleanup for test isolation.
    registry._finalized = False  # noqa: SLF001 - intentional internal cleanup for test isolation.

    container = get_container()
    container._providers.clear()  # noqa: SLF001 - intentional internal cleanup for test isolation.
    container._singletons.clear()  # noqa: SLF001 - intentional internal cleanup for test isolation.

    _BACKENDS.clear()


def reset_request_context(request: Any) -> None:
    """Clear per-request DFR state from ``request.state``."""

    state = getattr(request, "state", None)
    if state is None:
        return

    for attr in ("_dfr_context", "_dfr_auth", "_dfr_di_scope", "_csrf_processed", "_session_committed"):
        if hasattr(state, attr):
            delattr(state, attr)

    setattr(state, "_dfr_context", RequestContext())


@pytest.fixture(scope="session")
def dfr_app() -> Any:
    """Session-scoped DFR ASGI app fixture."""

    if DjangoClient is None:
        pytest.skip("Django is not available in this environment.")

    app = DFRApp(django_settings_module="tests.settings")
    app.bootstrap()
    return app.asgi()


@pytest.fixture(scope="function")
def dfr_client(dfr_app: Any) -> DFRTestClient:
    """Function-scoped sync test client fixture."""

    reset_app_state(dfr_app)
    return DFRTestClient(dfr_app)


@pytest.fixture(scope="function")
async def dfr_async_client(dfr_app: Any) -> Any:
    """Function-scoped async test client fixture."""

    if httpx is None:
        pytest.skip("httpx is not available in this environment.")

    reset_app_state(dfr_app)
    client = httpx.AsyncClient(app=dfr_app, base_url="http://testserver")
    try:
        yield client
    finally:
        # FOOTGUN: leaking unclosed async clients will keep event-loop resources alive across tests.
        await client.aclose()
