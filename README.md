# Search -> Scrape -> Crawl JSON API (Firecrawl + Scrapling + Go)

This project is a platform pipeline:
1. **Search** (Firecrawl API endpoint, self-host supported)
2. **Scrape** (Scrapling)
3. **Crawl/Fetch** (Go concurrent fetcher)
4. Return merged **JSON API** response

## No `FIRECRAWL_API_KEY` required
- By default this app calls local Firecrawl API URL: `http://127.0.0.1:3002/v1`.
- If your Firecrawl server requires auth, set `FIRECRAWL_API_KEY`.
- If auth is disabled, leave it empty.

## Endpoints
- `POST /search` : pipeline orchestration
- `POST /crawl`  : scrape/crawl URLs concurrently
- `GET /health`

## Example `/search`
```json
{
  "query": "python golang web crawling",
  "seed_urls": ["https://example.com", "https://example.org"],
  "max_urls": 5,
  "use_firecrawl": true,
  "use_scrapling": true,
  "use_go_fetch": true
}
```

## Render free deploy
Use the included Dockerfile. It runs FastAPI on `$PORT` and Go service on `8081`.
