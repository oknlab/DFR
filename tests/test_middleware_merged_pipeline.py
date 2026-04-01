import asyncio

from dfr.middleware import MergedMiddlewarePipeline


def test_merged_pipeline_native_and_django() -> None:
    pipeline = MergedMiddlewarePipeline()
    events: list[str] = []

    def native_factory(next_app):
        async def wrapped(scope, receive, send):
            events.append("native-in")
            await next_app(scope, receive, send)
            events.append("native-out")

        return wrapped

    async def django_like(scope, call_next):
        events.append("django-in")
        await call_next()
        events.append("django-out")

    async def app(scope, receive, send):
        events.append("terminal")

    pipeline.add_native("native", native_factory)
    pipeline.add_django("django", django_like)

    built = pipeline.build(app)
    asyncio.run(built({}, lambda: None, lambda _m: None))

    assert events == ["native-in", "django-in", "terminal", "django-out", "native-out"]
