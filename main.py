from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


FRONTEND_ORIGIN = "http://127.0.0.1:5500"
UPSTREAM_SEARCH_URL = "https://connectnet.onrender.com/search"

app = FastAPI(title="Secure Data Pipeline Bridge", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


class PipelineResponse(BaseModel):
    query: str = Field(description="Search query")
    stages: dict[str, Any] = Field(description="Pipeline stages and outputs")


async def fetch_upstream_json(q: str, format_: str = "json") -> tuple[str, Any]:
    params = {"q": q, "format": format_}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0)) as client:
            response = await client.get(UPSTREAM_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        return str(response.url), payload
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Upstream request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream service returned HTTP {exc.response.status_code}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Upstream returned malformed JSON") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Network error while reaching upstream") from exc


@app.get("/api/search")
async def proxy_search(
    q: str = Query(default="[]", description="Search query sent to upstream"),
    format: str = Query(default="json", pattern="^json$"),
) -> dict[str, Any]:
    source, payload = await fetch_upstream_json(q=q, format_=format)
    return {"source": source, "query": q, "data": payload}


@app.get("/api/pipeline", response_model=PipelineResponse)
async def pipeline_view(
    q: str = Query(default="[]", description="Pipeline input query"),
) -> PipelineResponse:
    """
    Logical pipeline view:
    search -> crawling -> scraping -> JSON API
    """
    source, payload = await fetch_upstream_json(q=q)

    stages: dict[str, Any] = {
        "search": {
            "status": "completed",
            "input": q,
            "output": f"Search request issued to {UPSTREAM_SEARCH_URL}",
        },
        "crawling": {
            "status": "completed",
            "output": "Remote service discovered and traversed matching resources.",
        },
        "scraping": {
            "status": "completed",
            "output": "Remote service extracted structured fields from crawled pages.",
        },
        "json_api": {
            "status": "completed",
            "source": source,
            "output": payload,
        },
    }

    return PipelineResponse(query=q, stages=stages)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
