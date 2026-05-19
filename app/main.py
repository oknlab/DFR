import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis

from app.web_search import (
    DEFAULT_ENGINE_KEY,
    get_search_context,
    get_search_engine,
    list_search_engines,
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
        logging.info("Connected to Redis at %s", REDIS_URL)
    except Exception as exc:
        app.state.redis = None
        logging.warning("Redis unavailable; continuing without cache: %s", exc)
    yield
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="DFR Search",
    description="A FastAPI search frontend with a JSON API and Redis caching.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "engines": list_search_engines(),
            "default_engine": DEFAULT_ENGINE_KEY,
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
    return {"status": "ok", "redis": redis_status}


@app.get("/api/engines")
async def engines():
    return {"default": DEFAULT_ENGINE_KEY, "engines": list_search_engines()}


@app.get("/api/search")
async def search(
    q: Annotated[str, Query(min_length=1, max_length=200, description="Search query")],
    max_results: Annotated[int, Query(ge=1, le=MAX_RESULTS_LIMIT)] = 5,
    engine: Annotated[str, Query(description="Search engine key")] = DEFAULT_ENGINE_KEY,
    crawl: Annotated[bool, Query(description="Crawl each result URL for richer content")] = True,
    lang: Annotated[Optional[str], Query(description="Language/locale hint for provider, e.g. en-US")] = None,
    safe: Annotated[Optional[str], Query(description="Safe-search hint for provider")] = None,
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    try:
        selected_engine = get_search_engine(engine)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    extra_params = {}
    if lang:
        extra_params["lang"] = lang
    if safe:
        extra_params["safe"] = safe

    results = await get_search_context(
        query=query,
        max_results=max_results,
        redis_client=app.state.redis,
        engine_key=selected_engine.key,
        crawl_pages=crawl,
        extra_params=extra_params or None,
    )
    return {
        "query": query,
        "engine": selected_engine.public_dict(),
        "count": len(results),
        "crawl": crawl,
        "params": extra_params,
        "results": results,
    }
