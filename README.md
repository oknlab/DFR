# DFR

DFR is a hybrid Python web framework that aims to unify Django, DRF, and FastAPI ergonomics under one ASGI-native surface.

## Current Status
This repository currently contains the **foundational framework skeleton**:
- ASGI app container (`DFR`) and route registration
- unified dispatcher with sync/async endpoint support
- dependency, middleware, permission, and throttling primitives
- serializer, OpenAPI, and testing client scaffolds
- pagination/filtering and backend/admin compatibility stubs

See `TODO.md` and `WORKLOG.md` for implementation status and next milestones.
