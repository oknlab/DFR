from dfr.routing import DjangoURLAdapter, django_path_to_regex


def test_django_path_to_regex_int_converter() -> None:
    converted = django_path_to_regex("/users/<int:id>/")
    match = converted.pattern.match("/users/42/")
    assert match is not None
    assert match.group("id") == "42"


def test_django_url_adapter_resolve() -> None:
    adapter = DjangoURLAdapter()

    def endpoint(**kwargs):
        return kwargs

    adapter.add("/posts/<str:slug>/", endpoint)
    resolved = adapter.resolve("/posts/hello/")
    assert resolved is not None
    fn, kwargs = resolved
    assert fn is endpoint
    assert kwargs == {"slug": "hello"}
