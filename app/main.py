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

app = FastAPI(title="Hybrid Search API", version="0.1.0")

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
GO_FETCH_URL = os.getenv("GO_FETCH_URL", "http://127.0.0.1:8081/fetch")


class SearchRequest(BaseModel):
    query: str
    urls: list[str] = Field(default_factory=list)
    max_urls: int = 5
    use_firecrawl: bool = True
    use_scrapling: bool = True
    use_go_fetch: bool = True


class CrawlRequest(BaseModel):
    urls: list[str]
    concurrency: int = 8
    timeout_sec: int = 12


def _strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def firecrawl_search(query: str, limit: int) -> dict[str, Any]:
    if not FIRECRAWL_API_KEY:
        return {"provider": "firecrawl", "enabled": False, "reason": "missing FIRECRAWL_API_KEY"}

    url = "https://api.firecrawl.dev/v1/search"
    headers = {"Authorization": f"Bearer {FIRECRAWL_API_KEY}"}
    payload = {"query": query, "limit": limit}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers=headers)
        return {"provider": "firecrawl", "enabled": True, "status": r.status_code, "data": r.json()}


async def scrapling_fetch(url: str) -> dict[str, Any]:
    if Fetcher is None:
        return {"url": url, "ok": False, "error": "scrapling unavailable"}

    def _run() -> dict[str, Any]:
        try:
            resp = Fetcher().get(url, timeout=12)
            text = _strip_html(resp.html or "")
            return {"url": url, "ok": True, "title": resp.title, "text": text[:2000]}
        except Exception as exc:
            return {"url": url, "ok": False, "error": str(exc)}

    return await asyncio.to_thread(_run)


async def go_fetch(urls: list[str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            r = await client.post(GO_FETCH_URL, json={"urls": urls})
            return {"provider": "go-fetch", "status": r.status_code, "data": r.json()}
        except Exception as exc:
            return {"provider": "go-fetch", "status": 0, "error": str(exc)}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl")
async def crawl(req: CrawlRequest) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(max(1, req.concurrency))

    async def one(url: str) -> dict[str, Any]:
        async with semaphore:
            return await scrapling_fetch(url)

    results = await asyncio.gather(*(one(u) for u in req.urls))
    return {"count": len(results), "results": results}


@app.post("/search")
async def search(req: SearchRequest) -> dict[str, Any]:
    urls = req.urls[: req.max_urls]
    tasks = []

    if req.use_firecrawl:
        tasks.append(firecrawl_search(req.query, req.max_urls))

    if req.use_scrapling and urls:
        tasks.append(asyncio.gather(*(scrapling_fetch(u) for u in urls)))

    if req.use_go_fetch and urls:
        tasks.append(go_fetch(urls))

    merged = await asyncio.gather(*tasks, return_exceptions=True)
    normalized = []
    for item in merged:
        if isinstance(item, Exception):
            normalized.append({"error": str(item)})
        else:
            normalized.append(item)

    return {"query": req.query, "sources": normalized}
