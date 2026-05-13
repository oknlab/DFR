# Distributed Web Data OS (All-in-one, Render Free)

Pipeline: **search -> crawling -> scraping -> JSON API**.

Built with:
- Go (fast API + crawler)
- Redis (cache + queue)
- OpenAPI endpoint (`/openapi.json`)
- Simple UI (`/ui`)
- Firecrawl integration (search discovery)
- Apify token support flag
- Firecrawl + Scrapling repos cloned in Docker image

## Endpoints
- `POST /pipeline`
- `GET /health`
- `GET /openapi.json`
- `GET /ui`

## Run on Render
Deploy with Docker. Exposed port is `10000`.

## Example body
```json
{"query":"ai agents","seed_urls":["https://example.com"],"max_urls":5,"use_firecrawl":true,"use_apify":false}
```
