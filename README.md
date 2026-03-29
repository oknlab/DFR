# DFR

DFR is a hybrid Python framework that unifies key concepts from:

- **Django** (ORM, auth, middleware, sessions, admin ecosystem)
- **Django REST Framework** (serializers, permissions, throttling, filtering, pagination)
- **FastAPI/Starlette** (ASGI-native execution model and modern async ergonomics)

The goal is a **single application surface** for mixed sync/async workloads without monkey-patching framework internals.

---

## Status

**Version:** `0.1.0` (scaffold + hardening baseline)

Current package modules:

- `dfr.__init__` (lazy top-level exports)
- `dfr.app`
- `dfr.routing`
- `dfr.middleware`
- `dfr.deps`
- `dfr.auth`
- `dfr.serializers`
- `dfr.permissions`
- `dfr.throttling`
- `dfr.filters`
- `dfr.pagination`
- `dfr.openapi`
- `dfr.testing`
- `dfr.sync`
- `dfr.types`

---

## Design Principles

1. **Adapter-first architecture**
   - Use public framework APIs and adapters.
   - No monkey-patching Django/DRF/FastAPI internals.

2. **Single-process ASGI runtime**
   - One routing table.
   - One middleware pipeline.
   - One OpenAPI schema.

3. **Safe async/sync boundaries**
   - `run_sync(...)` for sync work inside async flows.
   - Boundary guard prevents nested async/sync deadlock patterns.

4. **Strict typing + packaging hygiene**
   - PEP 561 marker (`dfr/py.typed`).
   - Strict mypy/pyright settings in `pyproject.toml`.

---

## Quick Start

### 1) Create app

```python
from dfr.app import DFRApp
from dfr.routing import route

app = DFRApp(django_settings_module="project.settings")

@route("GET", "/health", name="health")
async def health(request) -> dict[str, str]:
    return {"status": "ok"}

asgi_app = app.asgi()
```

### 2) Run with an ASGI server

```bash
uvicorn project.asgi:asgi_app --reload
```

---

## Public API (top-level)

DFR uses lazy exports in `dfr/__init__.py`:

```python
from dfr import (
    DFRApp,
    route,
    include_router,
    include_django_urls,
    ModelSchema,
    Depends,
    CurrentUser,
    generate_openapi,
)
```

This keeps `import dfr` lightweight in environments where optional runtime dependencies are not fully installed.

---

## Core Runtime Notes

### Routing

- Canonical registry normalizes path syntax between Django and FastAPI-style routes.
- Conflict detection runs during finalization/boot.
- Dispatch supports both async handlers and sync handlers (sync via `run_sync`).

### Middleware

- Unified stack wraps Django-style and ASGI-style middleware.
- Per-request DI scope starts before dispatch and closes in `finally`.
- Session/CSRF finalization occurs once per response path.

### Auth/Permissions

- Auth backends are pluggable and priority-ordered.
- Auth context is memoized per request.
- Permission checks support sync and async execution paths.

### Serializers

- `ModelSchema` compiles Django model metadata into Pydantic v2 schemas.
- `save_async` persists in one coarse sync boundary.
- Validation errors are normalized to a unified shape.

---

## Testing

The repository includes environment-aware tests under `tests/`.

```bash
pytest -q
```

Some tests are skipped automatically if optional dependencies (e.g. Django/asgiref/httpx) are unavailable in the local environment.

---

## Configuration

Common settings used by the scaffold:

- `DJANGO_SETTINGS_MODULE`
- `DFR_AUTH_ORDER` (`SESSION_FIRST` or `TOKEN_FIRST`)
- `DFR_THROTTLE_RATES` (e.g. `{"user": "100/min", "anon": "20/min"}`)

---

## Development Notes

- Python `3.11+` target.
- Type checking intended for strict mypy/pyright modes.
- Keep module exports explicit via `__all__`.
- Preserve locked hardening invariants (lazy exports, DI scope closure, backend dedupe, optional dependency guards).
