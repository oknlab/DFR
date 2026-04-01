import asyncio
from dataclasses import dataclass

from dfr.filtering import DRFFilterAdapter
from dfr.pagination import paginate_from_query
from dfr.permissions import AllowAny, DRFPermissionAdapter
from dfr.throttling import BaseThrottle, DRFThrottleAdapter


@dataclass
class Request:
    query_params: dict
    ident: str = "anon"


def test_permission_adapter() -> None:
    adapter = DRFPermissionAdapter(AllowAny())
    assert asyncio.run(adapter.has_permission(Request(query_params={}))) is True


def test_throttle_adapter() -> None:
    class OnePerMinute(BaseThrottle):
        rate = "1/m"

    adapter = DRFThrottleAdapter(OnePerMinute())
    req = Request(query_params={}, ident="ip:1")
    assert asyncio.run(adapter.allow_request(req)) is True
    assert asyncio.run(adapter.allow_request(req)) is False


def test_filter_adapter() -> None:
    adapter = DRFFilterAdapter()
    rows = [Request(query_params={}, ident="a"), Request(query_params={}, ident="b")]
    filtered = adapter.filter_queryset(Request(query_params={"ident": "a"}), rows)
    assert [r.ident for r in filtered] == ["a"]


def test_paginate_from_query() -> None:
    page = paginate_from_query(list(range(10)), page=2, page_size=4)
    assert page.items == [4, 5, 6, 7]
