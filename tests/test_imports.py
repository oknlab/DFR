from __future__ import annotations

import importlib.util

import pytest


pytestmark = pytest.mark.skipif(importlib.util.find_spec("django") is None, reason="Django not installed")


def test_package_imports() -> None:
    import dfr
    import dfr.app
    import dfr.routing
    import dfr.middleware
    import dfr.deps
    import dfr.auth
    import dfr.serializers
    import dfr.permissions
    import dfr.throttling
    import dfr.filters
    import dfr.pagination
    import dfr.openapi

    assert dfr.__version__ == "0.1.0"
