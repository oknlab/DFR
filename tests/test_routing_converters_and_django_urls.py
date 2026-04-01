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


def test_django_url_adapter_uses_injected_resolver() -> None:
    class Match:
        def __init__(self):
            self.func = lambda **kwargs: kwargs
            self.kwargs = {"pk": 9}
            self.args = ()

    class Resolver:
        def resolve(self, _path):
            return Match()

    adapter = DjangoURLAdapter()
    adapter.set_resolver(Resolver())

    fn, kwargs = adapter.resolve("/anything/")
    assert kwargs == {"pk": 9}
    assert fn(**kwargs) == {"pk": 9}
