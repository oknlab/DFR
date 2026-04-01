import asyncio

from dfr.deps import Depends, resolve_dependencies
from dfr.middleware import MiddlewareStack
from dfr.permissions import AllowAny
from dfr.throttling import BaseThrottle


def test_dep_resolution_with_cache() -> None:
    calls = {"n": 0}

    def make_value() -> int:
        calls["n"] += 1
        return 7

    dep = Depends(make_value)
    a, b = asyncio.run(resolve_dependencies(dep, dep))
    assert (a, b) == (7, 7)
    assert calls["n"] == 1


def test_middleware_stack_order() -> None:
    stack = MiddlewareStack()
    events: list[str] = []

    def first(next_app):
        async def app(scope, receive, send):
            events.append("first-in")
            await next_app(scope, receive, send)
            events.append("first-out")

        return app

    def second(next_app):
        async def app(scope, receive, send):
            events.append("second-in")
            await next_app(scope, receive, send)
            events.append("second-out")

        return app

    async def terminal(scope, receive, send):
        events.append("terminal")

    stack.add("first", first)
    stack.add("second", second)
    app = stack.build(terminal)
    asyncio.run(app({}, lambda: None, lambda _m: None))

    assert events == ["first-in", "second-in", "terminal", "second-out", "first-out"]


def test_allow_any_permission() -> None:
    permission = AllowAny()
    assert asyncio.run(permission.has_permission({})) is True


def test_base_throttle() -> None:
    class OnePerMinute(BaseThrottle):
        rate = "1/m"

    throttle = OnePerMinute()
    assert asyncio.run(throttle.allow_request({}, ident="ip:1")) is True
    assert asyncio.run(throttle.allow_request({}, ident="ip:1")) is False
