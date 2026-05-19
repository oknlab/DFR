# DFR Search Frontend

A FastAPI web frontend for a JSON search API with Redis-backed response caching.

## Run locally

```bash
docker compose up --build
```

Open <http://localhost:8000> for the web UI, or query the JSON API directly:

```bash
curl 'http://localhost:8000/api/search?q=fastapi&max_results=5'
```

## Endpoints

- `GET /` — HTML/CSS/JS search UI.
- `GET /api/search?q=<query>&max_results=<1-10>` — JSON search results.
- `GET /health` — health check including Redis status.
