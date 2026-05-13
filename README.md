# Mini Scrapling -> JSON API

Simple, working platform for scraping data to JSON using Scrapling.

## Endpoints
- `GET /health`
- `POST /scrape`
- `POST /crawl`

## Request examples
### `/scrape`
```json
{"url":"https://example.com"}
```

### `/crawl`
```json
{"urls":["https://example.com","https://example.org"],"concurrency":5}
```

## Run (Docker)
- Render free compatible (uses `$PORT`)
- Deploy this repository with Docker runtime.
