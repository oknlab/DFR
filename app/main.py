import asyncio
import hashlib
import json
import os
import re
import time
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from pydantic import BaseModel, Field

try:
    from scrapling import Fetcher
except Exception:
    Fetcher = None

app = FastAPI(title="Distributed Web Data OS", version="0.3.0")

GO_FETCH_URL = os.getenv("GO_FETCH_URL", "http://127.0.0.1:8081/fetch")
FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "http://127.0.0.1:3002/v1")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CACHE_TTL_SEC = int(os.getenv("CACHE_TTL_SEC", "900"))

rds = redis.from_url(REDIS_URL, decode_responses=True)


class PipelineRequest(BaseModel):
    query: str = ""
    seed_urls: list[str] = Field(default_factory=list)
    max_urls: int = 10
    use_firecrawl: bool = True
    use_go_crawl: bool = True
    use_scrapling: bool = True
    use_apify: bool = False


def _strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _cache_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return "pipeline:" + hashlib.sha256(raw).hexdigest()


async def firecrawl_search(query: str, limit: int) -> dict[str, Any]:
    url = f"{FIRECRAWL_API_URL}/search"
    headers = {"Content-Type": "application/json"}
    if FIRECRAWL_API_KEY:
        headers["Authorization"] = f"Bearer {FIRECRAWL_API_KEY}"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.post(url, json={"query": query, "limit": limit}, headers=headers)
            return {"provider": "firecrawl", "ok": res.is_success, "status": res.status_code, "data": res.json()}
        except Exception as exc:
            return {"provider": "firecrawl", "ok": False, "error": str(exc)}


async def apify_search(query: str, limit: int) -> dict[str, Any]:
    if not APIFY_TOKEN:
        return {"provider": "apify", "ok": False, "error": "missing APIFY_TOKEN"}
    # Lightweight JSON-first search using Apify datasets API pattern
    url = "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items"
    params = {"token": APIFY_TOKEN, "format": "json", "clean": "true"}
    payload = {"queries": query, "maxPagesPerQuery": 1, "resultsPerPage": max(1, min(limit, 10))}
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            res = await client.post(url, params=params, json=payload)
            data = res.json() if res.text else []
            return {"provider": "apify", "ok": res.is_success, "status": res.status_code, "data": data}
        except Exception as exc:
            return {"provider": "apify", "ok": False, "error": str(exc)}


async def go_crawl(urls: list[str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=45) as client:
        try:
            res = await client.post(GO_FETCH_URL, json={"urls": urls})
            return {"provider": "go-crawler", "ok": res.is_success, "status": res.status_code, "data": res.json()}
        except Exception as exc:
            return {"provider": "go-crawler", "ok": False, "error": str(exc)}


async def scrapling_scrape(url: str) -> dict[str, Any]:
    if Fetcher is None:
        return {"url": url, "ok": False, "error": "scrapling unavailable"}

    def _run() -> dict[str, Any]:
        try:
            resp = Fetcher().get(url, timeout=12)
            text = _strip_html(resp.html or "")
            return {"url": url, "ok": True, "title": getattr(resp, "title", ""), "text": text[:3000]}
        except Exception as exc:
            return {"url": url, "ok": False, "error": str(exc)}

    return await asyncio.to_thread(_run)


@app.get("/health")
async def health() -> dict[str, Any]:
    try:
        pong = await rds.ping()
    except Exception:
        pong = False
    return {"status": "ok", "redis": bool(pong)}


@app.post("/pipeline")
async def pipeline(req: PipelineRequest) -> dict[str, Any]:
    t0 = time.time()
    payload = req.model_dump()
    ck = _cache_key(payload)

    cached = await rds.get(ck)
    if cached:
        data = json.loads(cached)
        data["cache"] = "hit"
        return data

    # 1) SEARCH
    search_stage: dict[str, Any] = {}
    if req.use_firecrawl and req.query:
        search_stage["firecrawl"] = await firecrawl_search(req.query, req.max_urls)
    if req.use_apify and req.query:
        search_stage["apify"] = await apify_search(req.query, req.max_urls)

    discovered_urls = list(req.seed_urls)
    fc_data = search_stage.get("firecrawl", {}).get("data", {})
    if isinstance(fc_data, dict):
        for item in fc_data.get("data", [])[: req.max_urls]:
            u = item.get("url")
            if isinstance(u, str):
                discovered_urls.append(u)

    discovered_urls = list(dict.fromkeys(discovered_urls))[: req.max_urls]

    # 2) CRAWL (Go)
    crawl_stage: dict[str, Any] = {}
    if req.use_go_crawl and discovered_urls:
        crawl_stage = await go_crawl(discovered_urls)

    # 3) SCRAPE (Scrapling)
    scrape_stage: list[dict[str, Any]] = []
    if req.use_scrapling and discovered_urls:
        scrape_stage = await asyncio.gather(*(scrapling_scrape(u) for u in discovered_urls))

    result = {
        "product": "distributed-web-data-os",
        "query": req.query,
        "stages": {"search": search_stage, "crawl": crawl_stage, "scrape": scrape_stage},
        "urls": discovered_urls,
        "cache": "miss",
        "latency_ms": int((time.time() - t0) * 1000),
    }

    await rds.setex(ck, CACHE_TTL_SEC, json.dumps(result))
    await rds.lpush("pipeline:jobs", json.dumps({"query": req.query, "ts": int(time.time())}))
    return result
