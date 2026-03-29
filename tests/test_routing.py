from __future__ import annotations

import asyncio
import importlib.util

import pytest


def test_empty_registry_dispatch_error() -> None:
    if importlib.util.find_spec("asgiref") is None:
        pytest.skip("asgiref not installed")

    from dfr.routing import DispatchError, RouteRegistry

    async def _dispatch_missing() -> None:
        registry = RouteRegistry()
        with pytest.raises(DispatchError):
            await registry.dispatch(request=object(), path="/missing", method="GET")

    asyncio.run(_dispatch_missing())


def test_route_conflict_detection() -> None:
    if importlib.util.find_spec("asgiref") is None:
        pytest.skip("asgiref not installed")

    from dfr.routing import RouteRegistry
    from dfr.types import HandlerType

    registry = RouteRegistry()

    async def h1(request):
        return {"ok": True}

    async def h2(request):
        return {"ok": False}

    registry.register(path="/items/{id:int}", methods={"GET"}, handler=h1, handler_type=HandlerType.DFR_VIEW)
    with pytest.raises(Exception):
        registry.register(path="/items/{pk:int}", methods={"GET"}, handler=h2, handler_type=HandlerType.DFR_VIEW)
