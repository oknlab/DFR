# Hybrid Web Search API (Firecrawl + Scrapling + Go)

A fast API that combines:
- **Firecrawl** for high-quality extraction and crawl jobs.
- **Scrapling** for direct scraping fallback.
- A **Go fetch microservice** for concurrent low-latency page fetching.

Designed to run on **Render free tier** using a single `Dockerfile`.

## Features
- `POST /search` (Python/FastAPI): merge Firecrawl + Scrapling + Go fetch results.
- `POST /crawl` (Python/FastAPI): crawl a list of URLs concurrently.
- `POST /fetch` (Go): fast concurrent fetch + lightweight text extraction.

## API

### `POST /search`
Request:
```json
{
  "query": "best golang scraping libraries",
  "urls": ["https://example.com"],
  "max_urls": 5,
  "use_firecrawl": true,
  "use_scrapling": true,
  "use_go_fetch": true
}
```

### `POST /crawl`
Request:
```json
{
  "urls": ["https://example.com", "https://example.org"],
  "concurrency": 8,
  "timeout_sec": 12
}
```

## Environment Variables
- `PORT` (default `10000`) - Render web port.
- `GO_FETCH_URL` (default `http://127.0.0.1:8081/fetch`) - Go service endpoint.
- `FIRECRAWL_API_KEY` (optional) - enables Firecrawl calls.

## Local Run
```bash
docker build -t hybrid-search .
docker run --rm -p 10000:10000 \
  -e PORT=10000 \
  -e FIRECRAWL_API_KEY=your_key \
  hybrid-search
```

## Render
1. Create new **Web Service** from this repo.
2. Choose **Docker** runtime.
3. Set optional env var: `FIRECRAWL_API_KEY`.
4. Deploy.

Render will expose the app on `$PORT`, handled by FastAPI.
