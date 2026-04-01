from dataclasses import dataclass

from dfr.admin import build_admin_registration
from dfr.db.backends import PostgresBackend, PostgresBackendConfig
from dfr.filtering import apply_filters
from dfr.pagination import PageNumberPagination


@dataclass
class Item:
    id: int
    status: str


def test_page_number_pagination() -> None:
    paginator = PageNumberPagination()
    page = paginator.paginate(list(range(10)), page=2, page_size=3)
    assert page.items == [3, 4, 5]
    assert page.total_pages == 4


def test_apply_filters() -> None:
    rows = [Item(id=1, status="open"), Item(id=2, status="closed")]
    filtered = apply_filters(rows, status="open")
    assert [row.id for row in filtered] == [1]


def test_backend_connection_info() -> None:
    backend = PostgresBackend(PostgresBackendConfig(dsn="postgresql://localhost/db"))
    assert backend.connection_info()["max_size"] == 10


def test_admin_registration_tuple() -> None:
    model, admin_class = build_admin_registration(Item)
    assert model is Item
    assert admin_class is None
