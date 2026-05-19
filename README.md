# DFR Search Frontend

A FastAPI web frontend for a JSON search API with Redis-backed response caching and maximum provider extensibility.

## Run locally

```bash
docker compose up --build
```

Open <http://localhost:8000> for the web UI, or query the JSON API directly:

```bash
curl 'http://localhost:8000/api/search?q=fastapi&max_results=5&engine=connectnet'
```

## Endpoints

- `GET /` — HTML/CSS/JS search UI.
- `GET /api/search?q=<query>&max_results=<1-10>&engine=<key>` — JSON search results.
- `GET /api/engines` — enabled JSON search engines for the selector.
- `GET /health` — health check including Redis status.

## Configure more search engines

The app ships with the provided ConnectNet JSON search endpoint. Add other SearXNG-style or Google Custom Search JSON-compatible providers with environment variables:

```bash
export SEARXNG_SEARCH_URL='https://your-searxng.example/search'
export SEARCH_ENGINES_JSON='{"company":{"name":"Company Search","url":"https://search.example.com/search","description":"Internal JSON search"}}'
```

Each configured engine must accept `q` and `format=json` query parameters and return either a `results` array (`url`, `title`, `content`) or an `items` array (`link`, `title`, `snippet`).


### Level-MAX multi-engine support
Configure as many engines as needed via environment variables (`*_SEARCH_URL`) and/or `SEARCH_ENGINES_JSON`.
