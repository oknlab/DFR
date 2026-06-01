import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Optional
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis

from app.web_search import (
    ANONYMOUS_VIEW_PREFIX,
    DEFAULT_ENGINE_KEY,
    HIDE_PROMOTED_RESULTS,
    STRICT_PRIVACY_MODE,
    get_search_context,
    get_search_engine,
    list_bangs,
    list_search_engines,
    parse_ranking,
    parse_source_types,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MAX_RESULTS_LIMIT = int(os.getenv("MAX_RESULTS_LIMIT", "10"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await redis_client.ping()
        app.state.redis = redis_client
        logging.info("Connected to Redis")
    except Exception as exc:
        app.state.redis = None
        logging.warning("Redis unavailable; continuing without cache: %s", exc)
    yield
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="DFR Search",
    description="A private FastAPI search frontend with bangs, anonymous view, and ad-free JSON results.",
    version="2.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.middleware("http")
async def privacy_headers(request: Request, call_next):
    """Avoid cookies/tracking headers and keep strict browser privacy defaults."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "interest-cohort=(), browsing-topics=()"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    if STRICT_PRIVACY_MODE:
        response.headers.pop("set-cookie", None)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "engines": list_search_engines(),
            "bangs": list_bangs(),
            "default_engine": DEFAULT_ENGINE_KEY,
            "strict_privacy": STRICT_PRIVACY_MODE,
            "hide_promoted": HIDE_PROMOTED_RESULTS,
        },
    )


@app.get("/health")
async def health():
    redis_status = "disabled"
    if app.state.redis:
        try:
            await app.state.redis.ping()
            redis_status = "ok"
        except Exception:
            redis_status = "error"
    return {"status": "ok", "redis": redis_status, "strict_privacy": STRICT_PRIVACY_MODE}


@app.get("/api/engines")
async def engines():
    return {"default": DEFAULT_ENGINE_KEY, "engines": list_search_engines()}


@app.get("/api/bangs")
async def bangs():
    return {"bangs": list_bangs()}


@app.get("/api/privacy")
async def privacy():
    return {
        "tracking": False,
        "profiles": False,
        "cookies": False,
        "stores_ip": False,
        "ads": False,
        "promoted_results_hidden": HIDE_PROMOTED_RESULTS,
        "strict_privacy": STRICT_PRIVACY_MODE,
    }


@app.get("/api/anonymous")
async def anonymous_view(url: Annotated[str, Query(min_length=1, max_length=2000)]):
    """Open a URL without exposing the browser directly when no external proxy is configured."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Anonymous View only supports http(s) URLs")
    if not ANONYMOUS_VIEW_PREFIX.startswith("/"):
        return RedirectResponse(f"{ANONYMOUS_VIEW_PREFIX}{quote_plus(url)}", status_code=302)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20, cookies={}) as client:
            upstream = await client.get(
                url,
                headers={"User-Agent": "DFR-Anonymous-View", "DNT": "1", "Sec-GPC": "1"},
            )
            upstream.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Anonymous View could not fetch the page: {exc}") from exc

    content_type = upstream.headers.get("content-type", "text/html")
    if "text/html" not in content_type:
        return Response(content=upstream.content, media_type=content_type)

    soup = BeautifulSoup(upstream.text, "html.parser")
    for tag in soup(["script", "iframe", "form"]):
        tag.decompose()
    if soup.head:
        base = soup.new_tag("base", href=str(upstream.url))
        soup.head.insert(0, base)
    for tag_name, attr in (("a", "href"), ("img", "src"), ("link", "href")):
        for tag in soup.find_all(tag_name):
            if tag.get(attr):
                tag[attr] = urljoin(str(upstream.url), tag[attr])
    banner = soup.new_tag("div")
    banner.string = "Anonymous View: scripts/forms removed, no cookies stored by DFR Search."
    banner["style"] = (
        "position:sticky;top:0;z-index:2147483647;padding:10px;"
        "background:#e6f4ea;color:#137333;font:14px Arial"
    )
    if soup.body:
        soup.body.insert(0, banner)
    return HTMLResponse(str(soup))


@app.get("/api/search")
async def search(
    q: Annotated[str, Query(min_length=1, max_length=200, description="Search query")],
    max_results: Annotated[int, Query(ge=1, le=MAX_RESULTS_LIMIT)] = 5,
    engine: Annotated[str, Query(description="Search engine key or 'all'")] = DEFAULT_ENGINE_KEY,
    crawl: Annotated[bool, Query(description="Crawl each result URL for richer content")] = True,
    lang: Annotated[Optional[str], Query(description="Language/locale hint for provider, e.g. en-US")] = None,
    safe: Annotated[Optional[str], Query(description="Safe-search hint for provider")] = None,
    hide_promoted: Annotated[bool, Query(description="Hide ads/promoted/sponsored results")] = HIDE_PROMOTED_RESULTS,
    source_types: Annotated[
        Optional[str],
        Query(description="Comma-separated sources: web,docs,images,news,social"),
    ] = None,
    ranking: Annotated[
        Optional[str],
        Query(description="Stateless ranking hints, e.g. docs.python.org:10,example.com:-5"),
    ] = None,
    fallback: Annotated[bool, Query(description="Use configured Bing fallback when the selected engine is empty")] = True,
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    if engine != "all":
        try:
            selected_engine = get_search_engine(engine)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        engine_key = selected_engine.key
        engine_payload = selected_engine.public_dict()
    else:
        engine_key = "all"
        engine_payload = {"key": "all", "name": "All configured sources", "description": "Merged sources"}

    extra_params = {}
    if lang:
        extra_params["lang"] = lang
    if safe:
        extra_params["safe"] = safe

    results = await get_search_context(
        query=query,
        max_results=max_results,
        redis_client=app.state.redis,
        engine_key=engine_key,
        crawl_pages=crawl,
        extra_params=extra_params or None,
        hide_promoted=hide_promoted,
        source_types=parse_source_types(source_types),
        ranking=parse_ranking(ranking),
        use_fallback=fallback,
    )
    return {
        "query": query,
        "engine": engine_payload,
        "count": len(results),
        "crawl": crawl,
        "params": extra_params,
        "privacy": {
            "tracking": False,
            "profiles": False,
            "cookies": False,
            "stores_ip": False,
            "ad_free": hide_promoted,
            "strict": STRICT_PRIVACY_MODE,
        },
        "source_types": parse_source_types(source_types),
        "results": results,
    }
