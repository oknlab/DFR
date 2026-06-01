# OKNLAB Privacy Search

A full-stack privacy-first search engine UI built with Vue 3 (Composition API), Tailwind CSS, shadcn-vue-style components, DaisyUI, FastAPI, and Redis.

## Features

- No user tracking, cookies, profiling, or IP-address storage.
- Bangs (`!w`, `!yt`, `!amazon`) with a JSON-backed extension point.
- Independent search aggregation through `app/web_search.py`, with optional Bing fallback wiring.
- Hide promoted results toggle.
- Strict privacy mode.
- Anonymous View proxy links for results.
- Ad-free result rendering.
- Per-browser manual ranking stored locally in the UI, not on the server.
- Multi-source views for web, documents, images, news, and social results.
- JSON API data contract for all frontend/backend exchange.

## Run locally

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In another terminal:

```bash
# Optional: static frontend is served by FastAPI.
# If you prefer a Vite workflow, install packages in frontend/ and run npm run dev.
```

## Docker

```bash
docker compose up --build
```

The production container serves the Vue app and the FastAPI JSON API from the same origin.
