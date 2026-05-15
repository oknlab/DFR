from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


FRONTEND_ORIGIN = "http://127.0.0.1:5500"
UPSTREAM_BASE_URL = "https://connectnet.onrender.com/search"

app = FastAPI(title="Secure JSON Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)


class ProxyResponse(BaseModel):
    source: str = Field(description="Upstream source URL")
    query: str = Field(description="Query value sent to upstream")
    data: Any = Field(description="JSON payload returned by upstream")


@app.get("/api/search", response_model=ProxyResponse)
async def proxy_search(
    q: str = Query(default="[]", description="Search query sent to upstream"),
    format: str = Query(default="json", pattern="^json$"),
) -> ProxyResponse:
    params = {"q": q, "format": format}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            response = await client.get(UPSTREAM_BASE_URL, params=params)
        response.raise_for_status()
        payload = response.json()
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

    return ProxyResponse(source=str(response.url), query=q, data=payload)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
