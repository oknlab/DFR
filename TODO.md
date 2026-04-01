# DFR Todo Status

## Phase Completion Snapshot

### P0 — Core Runtime
- [x] Project scaffolding (`pyproject.toml`, package layout, CI, docs)
- [x] `dfr.app` ASGI application shell (`DFR`)
- [x] `dfr.async_` boundary helpers (`ORMExecutor`, `sync_to_async`, `async_to_sync`)
- [x] `dfr.routing.registry` route registration primitives
- [x] `dfr.routing.dispatcher` unified dispatcher (registry + Django adapter fallback)
- [x] `dfr.routing.converters` Django path converter support
- [x] `dfr.routing.django_urls` lightweight URL adapter

### P1 — Data & DI Foundations
- [x] `dfr.serializers` scaffold (`DFRSchema`, field metadata, nested resolver)
- [x] `dfr.deps.core` dependency container and caching
- [x] `dfr.deps.auth` current-user dependency helper
- [x] `dfr.deps.db` transaction wrapper helper
- [x] `dfr.deps.pagination` page params helper

### P2 — Cross-Cutting Runtime
- [x] `dfr.middleware` stack and entry model
- [x] `dfr.permissions` base + `AllowAny`
- [x] `dfr.throttling` in-memory throttle primitive

### P3 — Developer Experience
- [x] `dfr.testing` test client + fixture helper
- [x] `dfr.openapi` schema/sample generator + Django serializer stub
- [x] Baseline tests across routing/deps/middleware/serializers/pagination/filtering

### P4 — Ecosystem Bridges (Scaffolded)
- [x] `dfr.pagination` page-number implementation
- [x] `dfr.filtering` attribute-based filter helper
- [x] `dfr.db.backends.postgresql` backend config facade
- [x] `dfr.admin.compat` registration helper

---

## Continuation List (Next Todo)

1. [~] Replace serializer scaffold with full **Pydantic v2 model integration** (implemented with runtime guard; full execution requires pydantic availability).
2. [ ] Add **real Django URLResolver adapter** using Django resolver APIs (instead of lightweight stub).
3. [ ] Merge **FastAPI router ownership cache** with fallback Django adapter in dispatcher.
4. [ ] Add **ASGI middleware adapter layer** for real Django middleware compatibility.
5. [~] Add **auth convergence**: backend-chain dependency scaffold implemented; full Django session/auth integration pending.
6. [~] Add **DRF-compatible permission/throttle/filter/pagination adapters** (baseline adapters implemented; feature parity pending).
7. [~] Add **OpenAPI route introspection** from registered routes and dependency metadata (route registry introspection implemented; dependency metadata pending).
8. [~] Build **integration test project** (pytest-django) with end-to-end ASGI app checks (minimal Django URLResolver integration test scaffold added).
