import asyncio
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

try:
    from scrapling import Fetcher
except Exception:
    Fetcher = None

app = FastAPI(title="Search -> Scrape -> Crawl JSON API", version="0.2.0")

GO_FETCH_URL = os.getenv("GO_FETCH_URL", "http://127.0.0.1:8081/fetch")
FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL", "http://127.0.0.1:3002/v1")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")


class SearchRequest(BaseModel):
    query: str = ""
    seed_urls: list[str] = Field(default_factory=list)
    max_urls: int = 10
    use_firecrawl: bool = True
    use_scrapling: bool = True
    use_go_fetch: bool = True


class CrawlRequest(BaseModel):
    urls: list[str]
    concurrency: int = 8


def _strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def firecrawl_search(query: str, limit: int) -> dict[str, Any]:
    url = f"{FIRECRAWL_API_URL}/search"
    headers = {"Content-Type": "application/json"}
    if FIRECRAWL_API_KEY:
        headers["Authorization"] = f"Bearer {FIRECRAWL_API_KEY}"

    payload = {"query": query, "limit": limit}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(url, json=payload, headers=headers)
            data = r.json() if r.text else {}
            return {"provider": "firecrawl", "ok": r.is_success, "status": r.status_code, "data": data}
        except Exception as exc:
            return {"provider": "firecrawl", "ok": False, "error": str(exc)}


async def scrapling_fetch(url: str) -> dict[str, Any]:
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


async def go_fetch(urls: list[str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.post(GO_FETCH_URL, json={"urls": urls})
            return {"provider": "go-fetch", "ok": r.is_success, "status": r.status_code, "data": r.json()}
        except Exception as exc:
            return {"provider": "go-fetch", "ok": False, "error": str(exc)}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl")
async def crawl(req: CrawlRequest) -> dict[str, Any]:
    sem = asyncio.Semaphore(max(1, req.concurrency))

    async def one(u: str) -> dict[str, Any]:
        async with sem:
            return await scrapling_fetch(u)

    results = await asyncio.gather(*(one(u) for u in req.urls))
    return {"stage": "crawl", "count": len(results), "results": results}


@app.post("/search")
async def search(req: SearchRequest) -> dict[str, Any]:
    urls = req.seed_urls[: req.max_urls]

    firecrawl_task = firecrawl_search(req.query, req.max_urls) if req.use_firecrawl and req.query else None
    scrapling_task = asyncio.gather(*(scrapling_fetch(u) for u in urls)) if req.use_scrapling and urls else None
    go_task = go_fetch(urls) if req.use_go_fetch and urls else None

    out: dict[str, Any] = {"stage": "search", "query": req.query, "pipeline": {}}

    if firecrawl_task:
        out["pipeline"]["search"] = await firecrawl_task
    if scrapling_task:
        out["pipeline"]["scrape"] = await scrapling_task
    if go_task:
        out["pipeline"]["fetch"] = await go_task

    return out
