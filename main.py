from __future__ import annotations

from typing import Any, List

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError


# Update this to match your frontend host/port in production.
ALLOWED_ORIGINS = [
    "http://localhost:5500",  # VS Code Live Server (common)
    "http://127.0.0.1:5500",
    "http://localhost:3000",  # local dev frontend option
    "http://127.0.0.1:3000",
]

DEFAULT_TARGET_URL = "https://www.sofascore.com/api/v1/sport/football/events/live"
REQUEST_TIMEOUT_SECONDS = 10.0


class EventTournament(BaseModel):
    name: str | None = None


class EventStatus(BaseModel):
    type: str | None = None
    description: str | None = None


class Team(BaseModel):
    name: str | None = None


class LiveEvent(BaseModel):
    id: int
    slug: str | None = None
    homeTeam: Team | None = None
    awayTeam: Team | None = None
    status: EventStatus | None = None
    tournament: EventTournament | None = None


class LiveEventsResponse(BaseModel):
    events: List[LiveEvent] = Field(default_factory=list)


app = FastAPI(title="Secure JSON Proxy Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/live-events", response_model=LiveEventsResponse)
async def get_live_events(
    target_url: str = Query(
        default=DEFAULT_TARGET_URL,
        description="Remote JSON endpoint. Keep this restricted in production.",
    )
) -> LiveEventsResponse:
    """
    Server-side proxy for remote JSON data.

    This avoids browser CORS issues because the frontend calls FastAPI,
    and FastAPI performs the cross-origin request server-side.
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                target_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "FastAPI-JSON-Bridge/1.0",
                },
            )
            response.raise_for_status()

        payload: Any = response.json()

        # Validate known schema (events list) and normalize output.
        try:
            return LiveEventsResponse.model_validate(payload)
        except ValidationError:
            if isinstance(payload, dict) and isinstance(payload.get("events"), list):
                # Best effort: pass through only events list if top-level shape differs.
                return LiveEventsResponse(events=payload["events"])
            raise

    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Upstream request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned HTTP {exc.response.status_code}",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Schema validation failed: {exc.errors()}") from exc
    except ValueError as exc:
        # JSON decode errors land here.
        raise HTTPException(status_code=502, detail="Upstream returned malformed JSON") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected proxy error") from exc
