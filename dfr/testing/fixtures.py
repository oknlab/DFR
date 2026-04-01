"""Pytest fixture helpers for DFR."""

from __future__ import annotations

from dfr.app import DFR
from dfr.conf import DFRConfig
from dfr.testing.client import DFRTestClient


def create_test_client() -> DFRTestClient:
    """Create a default DFR app + test client pair."""
    app = DFR(DFRConfig(django_settings_module="tests.settings"))
    return DFRTestClient(app)


__all__ = ["create_test_client"]
