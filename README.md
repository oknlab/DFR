# Distributed Web Data OS (Render-ready)

If previous build didn't work, this version fixes runtime issues and uses `PORT` env required by Render.

Pipeline: **search -> crawling -> scraping -> JSON API**

## Endpoints
- `POST /pipeline`
- `GET /health`
- `GET /openapi.json`
- `GET /ui`

## Works without Firecrawl
You can run with only `seed_urls` and `use_firecrawl:false`.

## Example
```json
{"query":"","seed_urls":["https://example.com","https://example.org"],"max_urls":5,"use_firecrawl":false,"use_apify":false}
```

## Render
- Docker deploy
- Service port comes from `PORT` env (handled by app)
