FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic

RUN cat > /app/main.py <<'PY'
from __future__ import annotations

from pathlib import Path
from typing import Any, List
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

ALLOWED_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
DEFAULT_TARGET_URL = "https://www.sofascore.com/api/v1/sport/football/events/live"
REQUEST_TIMEOUT_SECONDS = 15.0


class EventTournament(BaseModel):
    name: str | None = None


class EventStatus(BaseModel):
    type: str | None = None
    description: str | None = None


class Team(BaseModel):
    name: str | None = None


class LiveEvent(BaseModel):
    id: int | None = None
    slug: str | None = None
    homeTeam: Team | None = None
    awayTeam: Team | None = None
    status: EventStatus | None = None
    tournament: EventTournament | None = None


class LiveEventsResponse(BaseModel):
    events: List[LiveEvent] = Field(default_factory=list)


app = FastAPI(title="Secure JSON Proxy Bridge", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization"],
)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/live-events", response_model=LiveEventsResponse)
async def get_live_events(
    target_url: str = Query(default=DEFAULT_TARGET_URL, description="Any absolute HTTP(S) JSON endpoint"),
) -> LiveEventsResponse:
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="target_url must be an absolute http(s) URL")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(
                target_url,
                headers={
                    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                    "Referer": "https://www.google.com/",
                    "Origin": "https://www.google.com",
                },
            )
            response.raise_for_status()

        payload: Any = response.json()

        if isinstance(payload, list):
            return LiveEventsResponse(events=payload)

        if isinstance(payload, dict) and isinstance(payload.get("events"), list):
            return LiveEventsResponse.model_validate(payload)

        raise HTTPException(
            status_code=502,
            detail="Upstream JSON is valid but does not match expected schema: {'events': [...]} or [...].",
        )

    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Upstream request timed out") from exc
    except httpx.HTTPStatusError as exc:
        body_preview = exc.response.text[:180].replace("\n", " ")
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned HTTP {exc.response.status_code}. Body preview: {body_preview}",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Schema validation failed: {exc.errors()}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Upstream returned malformed JSON") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected proxy error") from exc
PY

RUN cat > /app/index.html <<'HTML'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Live Football Events (FastAPI Proxy)</title>
  </head>
  <body>
    <main>
      <h1>Live Football Events</h1>
      <input id="urlInput" style="width: 100%; max-width: 780px" value="https://www.sofascore.com/api/v1/sport/football/events/live" />
      <button id="loadBtn">Load Live Events</button>
      <p id="status"></p>
      <p id="error" style="color: #b00020"></p>
      <section id="events"></section>
    </main>

    <script>
      const API_BASE = window.location.origin;
      const loadBtn = document.getElementById('loadBtn');
      const urlInput = document.getElementById('urlInput');
      const eventsRoot = document.getElementById('events');
      const errorRoot = document.getElementById('error');
      const statusRoot = document.getElementById('status');

      function renderEvents(events) {
        eventsRoot.innerHTML = '';
        if (!Array.isArray(events) || events.length === 0) {
          eventsRoot.textContent = 'No live events available right now.';
          return;
        }
        events.forEach((event) => {
          const article = document.createElement('article');
          const home = event?.homeTeam?.name || 'Home Team';
          const away = event?.awayTeam?.name || 'Away Team';
          const tournament = event?.tournament?.name || 'Unknown Tournament';
          const status = event?.status?.description || event?.status?.type || 'Unknown Status';
          article.textContent = `${home} vs ${away} | ${tournament} | ${status}`;
          eventsRoot.appendChild(article);
        });
      }

      async function loadLiveEvents() {
        errorRoot.textContent = '';
        statusRoot.textContent = 'Loading...';
        loadBtn.disabled = true;
        try {
          const targetUrl = encodeURIComponent(urlInput.value.trim());
          const response = await fetch(`${API_BASE}/api/live-events?target_url=${targetUrl}`, {
            method: 'GET',
            headers: { Accept: 'application/json' }
          });

          if (!response.ok) {
            let detail = '';
            try {
              const err = await response.json();
              detail = err?.detail ? `: ${err.detail}` : '';
            } catch (_) {}
            throw new Error(`Proxy failed with HTTP ${response.status}${detail}`);
          }

          const data = await response.json();
          renderEvents(data.events);
          statusRoot.textContent = `Loaded ${data.events?.length || 0} event(s).`;
        } catch (error) {
          errorRoot.textContent = `Failed to load events: ${error.message}`;
          statusRoot.textContent = '';
        } finally {
          loadBtn.disabled = false;
        }
      }

      loadBtn.addEventListener('click', loadLiveEvents);
    </script>
  </body>
</html>
HTML

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
