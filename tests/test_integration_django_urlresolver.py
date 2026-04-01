import importlib.util
import os

import pytest

from dfr.routing import DjangoURLAdapter

HAS_DJANGO = importlib.util.find_spec("django") is not None


@pytest.mark.skipif(not HAS_DJANGO, reason="django not installed in runtime")
def test_django_urlresolver_integration() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.integration.django_settings")

    import django

    django.setup()

    adapter = DjangoURLAdapter()
    adapter.load_urlconf("tests.integration.urls")

    resolved = adapter.resolve("/ping/")
    assert resolved is not None
    endpoint, kwargs = resolved
    assert endpoint.__name__ == "ping"
    assert kwargs == {}
