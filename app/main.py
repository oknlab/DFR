import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote, unquote, urlparse

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.web_search import BROWSER_HEADERS, get_search_context

ROOT = Path(__file__).resolve().parent.parent
BANGS_FILE = ROOT / "data" / "bangs.json"
STATIC_DIR = ROOT / "frontend"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STRICT_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), browsing-topics=()",
    "X-Content-Type-Options": "nosniff",
}


class Bang(BaseModel):
    bang: str
    name: str
    url: str
    category: str = "general"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_results: int = Field(8, ge=1, le=20)
    hide_promoted: bool = False
    strict_privacy: bool = True
    rankings: dict[str, int] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    bang_redirect: str | None = None
    results: list[dict]
    sources: dict[str, list[dict]]
    privacy: dict[str, str | bool]
    google_proxy_url: str
    fallback_used: bool = False


def load_bangs() -> list[Bang]:
    with BANGS_FILE.open() as file:
        return [Bang(**item) for item in json.load(file)]


def find_bang(query: str, bangs: list[Bang]) -> tuple[Bang, str] | None:
    parts = query.strip().split(maxsplit=1)
    if not parts:
        return None
    bang_key = parts[0].lower()
    for bang in bangs:
        if bang.bang.lower() == bang_key:
            return bang, parts[1] if len(parts) > 1 else ""
    return None


def apply_rankings(results: list[dict], rankings: dict[str, int]) -> list[dict]:
    def score(result: dict) -> tuple[int, str]:
        domain = urlparse(result.get("url", "")).netloc.replace("www.", "")
        return (-rankings.get(domain, 0), result.get("title", ""))

    return sorted(results, key=score)


def proxy_url(url: str) -> str:
    return f"/api/anonymous?url={quote(url, safe='')}"


def with_anonymous_links(results: list[dict]) -> list[dict]:
    shaped = []
    for result in results:
        clone = {**result}
        if clone.get("url"):
            clone["anonymous_url"] = proxy_url(clone["url"])
        shaped.append(clone)
    return shaped


async def get_redis(request: Request) -> Redis | None:
    return getattr(request.app.state, "redis", None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = None
    try:
        app.state.redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await app.state.redis.ping()
        logging.info("Connected to Redis cache")
    except Exception as exc:
        logging.warning("Redis unavailable; continuing without cache: %s", exc)
        app.state.redis = None
    yield
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="OKNLAB Privacy Search JSON API",
    version="1.0.0",
    description="A no-tracking search API with bangs, anonymous views, Redis caching, and multi-source result buckets.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in STRICT_SECURITY_HEADERS.items():
        response.headers[key] = value
    response.delete_cookie("session")
    return response


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "oknlab-search"}


@app.get("/api/bangs", response_model=list[Bang])
async def bangs() -> list[Bang]:
    return load_bangs()


@app.post("/api/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    redis: Annotated[Redis | None, Depends(get_redis)],
) -> SearchResponse:
    bangs = load_bangs()
    bang_match = find_bang(payload.query, bangs)
    if bang_match:
        bang, remainder = bang_match
        redirect = bang.url.format(query=quote(remainder))
        return SearchResponse(
            query=payload.query,
            bang_redirect=proxy_url(redirect) if payload.strict_privacy else redirect,
            results=[],
            sources={"web": [], "documents": [], "images": [], "news": [], "social": []},
            privacy={"tracking": False, "cookies": False, "ip_storage": False, "profiling": False},
            google_proxy_url=proxy_url(f"https://www.google.com/search?q={quote(payload.query)}"),
            fallback_used=False,
        )

    search_data = await get_search_context(
        payload.query,
        max_results=payload.max_results,
        redis_client=redis,
        hide_promoted=payload.hide_promoted,
    )
    ranked_results = with_anonymous_links(
        apply_rankings(search_data.get("results", []), payload.rankings)
    )
    sources = search_data.get("sources", {})
    for key, values in list(sources.items()):
        sources[key] = with_anonymous_links(values)
    return SearchResponse(
        query=payload.query,
        results=ranked_results,
        sources=sources,
        privacy={"tracking": False, "cookies": False, "ip_storage": False, "profiling": False},
        google_proxy_url=proxy_url(f"https://www.google.com/search?q={quote(payload.query)}"),
        fallback_used=search_data.get("fallback_used", False),
    )


@app.get("/api/anonymous")
async def anonymous_view(
    url: Annotated[str, Query(min_length=8, max_length=2048)],
    mode: Literal["redirect", "proxy"] = "redirect",
):
    target = unquote(url)
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Only absolute http(s) URLs can be opened anonymously")
    if mode == "redirect":
        return RedirectResponse(target, headers={"Referrer-Policy": "no-referrer"})

    async def stream():
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=20) as client:
            async with client.stream("GET", target) as upstream:
                async for chunk in upstream.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/html", headers={"Referrer-Policy": "no-referrer"})


if STATIC_DIR.exists():
    app.mount("/src", StaticFiles(directory=STATIC_DIR / "src"), name="src")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        asset = STATIC_DIR / full_path
        if full_path and asset.exists() and asset.is_file():
            return FileResponse(asset)
        return FileResponse(STATIC_DIR / "index.html")
