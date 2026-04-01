import asyncio
from types import SimpleNamespace

from dfr.deps import DjangoSessionAuthDependency


def test_session_auth_dependency() -> None:
    users = {"1": {"id": 1, "username": "alice"}}

    def loader(user_id):
        return users.get(str(user_id))

    request = SimpleNamespace(session={"_auth_user_id": "1"})
    dep = DjangoSessionAuthDependency(loader)
    user = asyncio.run(dep(request))
    assert user == {"id": 1, "username": "alice"}


def test_session_auth_missing_session() -> None:
    dep = DjangoSessionAuthDependency(lambda _uid: None)
    request = SimpleNamespace()
    assert asyncio.run(dep(request)) is None
