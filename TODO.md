# DFR Todo Status

## Completed Foundation
- [x] Project scaffolding (`pyproject.toml`, package layout, tests bootstrap)
- [x] Core ASGI app (`dfr.app.DFR`)
- [x] Routing primitives and dispatcher (`dfr.routing`)
- [x] Async boundary helpers (`dfr.async_`)
- [x] Dependency primitives (`dfr.deps.core`)
- [x] Middleware stack, permissions, throttling basics
- [x] Serializer bridge, OpenAPI and testing client scaffolds
- [x] Pagination, filtering, DB backend/admin compatibility stubs

## Remaining Integration Work
- [ ] Django URLResolver adapter and converter compatibility with `path()`/`re_path()`
- [ ] FastAPI router interoperability and OpenAPI route merging
- [ ] Full Pydantic v2-backed serializer validation model
- [ ] Django auth/session middleware bridge for ASGI scopes
- [ ] DRF-compatible permissions/throttling/filtering/pagination adapters
- [ ] End-to-end integration tests against real Django test project
