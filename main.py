"""
main.py - OKNLAB Search Engine API
FastAPI + Redis caching. No tracking, no cookies, no IP logging.
Built by OKNLAB.
"""

import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from web_search import (
    generate_cache_key,
    get_suggestions,
    proxy_fetch,
    unified_search,
)

# ─── Configuration ──────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5 minutes
UI_FILE = Path(__file__).parent / "ui.html"


# ─── Redis Connection ───────────────────────────────────────────────────────

redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    global redis_client
    try:
        redis_client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )
        await redis_client.ping()
        print(f"[✓] Redis connected: {REDIS_URL}")
    except Exception as e:
        print(f"[!] Redis unavailable ({e}), running without cache")
        redis_client = None

    yield

    if redis_client:
        await redis_client.close()
        print("[✓] Redis disconnected")


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="OKNLAB Search",
    description="Private, ad-free search engine. Built by OKNLAB.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,        # Disable docs for privacy
    redoc_url=None,
    openapi_url=None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Privacy Middleware ──────────────────────────────────────────────────────

@app.middleware("http")
async def privacy_middleware(request: Request, call_next):
    """
    Strip all tracking headers, ensure no cookies are set,
    never log IP addresses.
    """
    response = await call_next(request)

    # Privacy headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-DNS-Prefetch-Control"] = "off"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), "
        "interest-cohort=(), browsing-topics=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdn.jsdelivr.net https://cdn.tailwindcss.com "
        "https://unpkg.com https://images.unsplash.com "
        "https://images.pexels.com https://www.google.com; "
        "img-src * data: blob:; "
        "connect-src 'self'; "
        "frame-src 'self';"
    )

    # NEVER set cookies
    if "set-cookie" in response.headers:
        del response.headers["set-cookie"]

    # No server identification
    response.headers["Server"] = "OKNLAB-Search"

    return response


# ─── Cache Helpers ───────────────────────────────────────────────────────────

async def cache_get(key: str) -> dict | None:
    if not redis_client:
        return None
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


async def cache_set(key: str, value: dict, ttl: int = CACHE_TTL):
    if not redis_client:
        return
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the search UI. No cookies, no tracking."""
    try:
        content = UI_FILE.read_text(encoding="utf-8")
        return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>OKNLAB Search - UI not found</h1>",
            status_code=500,
        )


@app.post("/api/search")
async def search_endpoint(request: Request):
    """
    Main search endpoint.
    Accepts JSON body, returns results.
    NO IP logging, NO cookies, NO user profiling.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"results": [], "meta": {"error": "Invalid request body"}},
            status_code=400,
        )

    query = str(body.get("query", "")).strip()
    if not query:
        return JSONResponse({"results": [], "meta": {"error": "Empty query"}})

    source = body.get("source", "web")
    if source not in ("web", "images", "news", "social", "docs"):
        source = "web"

    hide_promoted = bool(body.get("hide_promoted", True))
    strict_privacy = bool(body.get("strict_privacy", True))
    fallback_provider = body.get("fallback_provider", "bing")
    per_page = min(int(body.get("per_page", 20)), 50)
    page = max(int(body.get("page", 1)), 1)

    # Rankings (client-provided, NEVER stored server-side)
    rankings = body.get("rankings", {}) if not strict_privacy else {}

    # Check cache
    cache_key = generate_cache_key(query, source, fallback_provider, page)
    cached = await cache_get(cache_key)
    if cached:
        cached["meta"]["cached"] = True
        # Apply rankings even on cached results (rankings are client-side)
        if rankings:
            import urllib.parse
            for r in cached.get("results", []):
                try:
                    domain = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                    r["score"] = r.get("score", 0) + rankings.get(domain, 0) * 2.0
                except Exception:
                    pass
            cached["results"].sort(key=lambda x: x.get("score", 0), reverse=True)
        return JSONResponse(cached)

    # Perform search
    result = await unified_search(
        query=query,
        source_type=source,
        hide_promoted=hide_promoted,
        fallback_provider=fallback_provider,
        limit=per_page,
        rankings=rankings if not strict_privacy else None,
    )

    # Cache (without personalized rankings data)
    cache_data = {
        "results": result["results"],
        "meta": result["meta"],
    }
    await cache_set(cache_key, cache_data)

    return JSONResponse(result)


@app.get("/api/suggest")
async def suggest_endpoint(q: str = ""):
    """Search suggestions. No tracking."""
    if len(q) < 2:
        return JSONResponse({"suggestions": []})

    # Check cache
    cache_key = f"suggest:{hashlib.sha256(q.encode()).hexdigest()[:12]}"
    cached = await cache_get(cache_key)
    if cached:
        return JSONResponse(cached)

    suggestions = await get_suggestions(q)
    result = {"suggestions": suggestions}
    await cache_set(cache_key, result, ttl=600)  # 10 min cache

    return JSONResponse(result)


@app.get("/api/proxy")
async def proxy_endpoint(url: str = ""):
    """
    Anonymous View proxy.
    Fetches URL server-side, strips trackers, returns clean content.
    No user IP or cookies forwarded.
    """
    if not url:
        return Response(content="Missing URL", status_code=400)

    # Validate URL
    if not url.startswith(("http://", "https://")):
        return Response(content="Invalid URL", status_code=400)

    result = await proxy_fetch(url)

    content = result["content"]
    if isinstance(content, str):
        content = content.encode("utf-8")

    return Response(
        content=content,
        status_code=result.get("status", 200),
        media_type=result.get("content_type", "text/html"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Proxy-Source": "OKNLAB-Anonymous-View",
            "Referrer-Policy": "no-referrer",
        },
    )


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass

    return JSONResponse({
        "status": "healthy",
        "redis": "connected" if redis_ok else "unavailable",
        "engine": "OKNLAB Search v1.0",
        "privacy": {
            "tracking": False,
            "cookies": False,
            "ip_logging": False,
            "user_profiling": False,
            "ad_free": True,
        },
        "built_by": "OKNLAB",
    })


@app.get("/api/config")
async def config_endpoint():
    """Public config - what the engine supports."""
    return JSONResponse({
        "name": "OKNLAB Search",
        "version": "1.0.0",
        "built_by": "OKNLAB",
        "features": [
            "no_tracking",
            "no_cookies",
            "no_ip_logging",
            "no_user_profiling",
            "ad_free",
            "anonymous_proxy_view",
            "bang_shortcuts",
            "hide_promoted_results",
            "personalized_ranking_client_side",
            "multi_source_search",
            "independent_index",
            "bing_fallback",
            "google_proxy_fallback",
            "duckduckgo_fallback",
            "strict_privacy_mode",
        ],
        "sources": ["web", "images", "news", "social", "docs"],
        "fallback_providers": ["independent", "bing", "google_proxy", "duckduckgo"],
    })
