# Distributed Web Data OS (JSON-first API)

All-in-one platform:
**search -> crawling -> scraping -> JSON API**

Stack merged in one service:
- Firecrawl (search / discovery)
- Go crawler (fast concurrent crawling)
- Scrapling (deep scraping)
- Redis (cache + job queue primitives)
- Optional Apify search provider

## API
- `POST /pipeline` (main orchestration endpoint)
- `GET /health`

## `POST /pipeline` example
```json
{
  "query": "best golang crawling libs",
  "seed_urls": ["https://example.com"],
  "max_urls": 10,
  "use_firecrawl": true,
  "use_go_crawl": true,
  "use_scrapling": true,
  "use_apify": false
}
```

## Env
- `PORT` (default `10000`)
- `REDIS_URL` (default `redis://127.0.0.1:6379/0`)
- `CACHE_TTL_SEC` (default `900`)
- `FIRECRAWL_API_URL` (default `http://127.0.0.1:3002/v1`)
- `FIRECRAWL_API_KEY` (optional)
- `APIFY_TOKEN` (optional)

## Render free
Use Docker deploy with this repo. Single container runs Redis + Go crawler + FastAPI.
