import asyncio
from types import SimpleNamespace

from dfr.deps import DjangoAuthDependency, RequireAuthenticatedUser


def test_django_auth_dependency_backend_chain() -> None:
    req = SimpleNamespace(token="abc")

    def backend1(_request):
        return None

    async def backend2(request):
        return {"user": request.token}

    auth = DjangoAuthDependency([backend1, backend2])
    user = asyncio.run(auth(req))
    assert user == {"user": "abc"}


def test_require_authenticated_user_raises() -> None:
    auth = DjangoAuthDependency([])
    req = SimpleNamespace()

    try:
        asyncio.run(RequireAuthenticatedUser(auth)(req))
        assert False, "Expected PermissionError"
    except PermissionError:
        assert True
