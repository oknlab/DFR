# DFR Architecture (Current Foundation)

## Runtime Layers
1. **Application container**: `dfr.app.DFR`
2. **Dispatch layer**: `dfr.routing.UnifiedDispatcher`
3. **Execution boundaries**: `dfr.async_.sync_to_async` / `ORMExecutor`
4. **Cross-cutting concerns**: middleware, dependencies, permissions, throttling
5. **Data surface**: serializers, pagination, filtering, OpenAPI helpers

## Current Design Notes
- The dispatcher currently performs direct route table scans by path and method.
- Sync endpoint invocation is centralized behind `sync_to_async` to avoid ad-hoc event-loop blocking.
- Dependency resolution supports request-scope caching semantics keyed by dependency+kwargs.
- Middleware stack composes ASGI callables in deterministic order.

## Next Steps
- Integrate Django URL resolving and FastAPI router ownership strategy.
- Replace serializer scaffolding with fully Pydantic-v2-backed contracts once dependency availability is guaranteed.
- Add integration tests with a real Django settings module and auth/session middleware.
