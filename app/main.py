import asyncio
import re
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from scrapling import Fetcher

app = FastAPI(title="Mini Scrapling JSON API", version="1.0.0")
fetcher = Fetcher()


class ScrapeRequest(BaseModel):
    url: str


class CrawlRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    concurrency: int = 5


def clean_text(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def scrape_one(url: str) -> dict[str, Any]:
    try:
        r = fetcher.get(url, timeout=15)
        text = clean_text(r.html or "")[:4000]
        return {
            "url": url,
            "ok": True,
            "status": getattr(r, "status", None),
            "title": getattr(r, "title", ""),
            "text": text,
        }
    except Exception as exc:
        return {"url": url, "ok": False, "error": str(exc)}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape")
async def scrape(req: ScrapeRequest) -> dict[str, Any]:
    result = await asyncio.to_thread(scrape_one, req.url)
    return {"result": result}


@app.post("/crawl")
async def crawl(req: CrawlRequest) -> dict[str, Any]:
    sem = asyncio.Semaphore(max(1, req.concurrency))

    async def one(u: str) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(scrape_one, u)

    results = await asyncio.gather(*(one(u) for u in req.urls))
    return {"count": len(results), "results": results}
