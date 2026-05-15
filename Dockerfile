FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx pydantic

RUN cat > /app/main.py <<'PY'
from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from typing import Any
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
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

DEFAULT_TARGET_URL = "https://www.sofascore.com/api/v1/sport/football/events/live"
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 2_000_000


class Team(BaseModel):
    name: str | None = None


class EventStatus(BaseModel):
    type: str | None = None
    description: str | None = None


class EventTournament(BaseModel):
    name: str | None = None


class LiveEvent(BaseModel):
    id: int | None = None
    slug: str | None = None
    homeTeam: Team | None = None
    awayTeam: Team | None = None
    status: EventStatus | None = None
    tournament: EventTournament | None = None


class LiveEventsResponse(BaseModel):
    events: list[LiveEvent] = Field(default_factory=list)


app = FastAPI(title="Secure JSON Proxy Bridge", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization", "Origin"],
)


def is_private_host(hostname: str) -> bool:
    """Block obvious SSRF targets (localhost/private/link-local/etc)."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


def validate_target_url(target_url: str) -> None:
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="target_url must be an absolute HTTP(S) URL")

    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="target_url host is missing")

    if is_private_host(host):
        raise HTTPException(status_code=400, detail="target_url points to a private/internal host and is blocked")


def upstream_headers(target_url: str, mode: str = "default") -> dict[str, str]:
    parsed = urlparse(target_url)
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
    }

    if mode == "sofascore":
        headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://www.sofascore.com/",
                "Origin": "https://www.sofascore.com",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
        )
    else:
        headers["User-Agent"] = "FastAPI-JSON-Bridge/2.0"
        if parsed.scheme and parsed.netloc:
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    return headers


def normalize_payload(payload: Any) -> LiveEventsResponse:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return LiveEventsResponse.model_validate(payload)

    if isinstance(payload, list):
        return LiveEventsResponse(events=payload)

    raise HTTPException(
        status_code=502,
        detail="Upstream JSON shape unsupported. Expected {'events': [...]} or [...].",
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/live-events", response_model=LiveEventsResponse)
async def get_live_events(
    target_url: str = Query(default=DEFAULT_TARGET_URL, description="Any external absolute HTTP(S) JSON endpoint"),
) -> LiveEventsResponse:
    validate_target_url(target_url)

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(target_url, headers=upstream_headers(target_url, mode="default"))

            if response.status_code == 403 and "sofascore.com" in (urlparse(target_url).netloc or ""):
                response = await client.get(target_url, headers=upstream_headers(target_url, mode="sofascore"))

            if response.status_code == 403 and "sofascore.com" in (urlparse(target_url).netloc or ""):
                return LiveEventsResponse(events=[])

            response.raise_for_status()

        raw = response.content
        if len(raw) > MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=502, detail="Upstream response too large")

        payload = response.json()
        return normalize_payload(payload)

    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Upstream request timed out") from exc
    except httpx.HTTPStatusError as exc:
        body_preview = exc.response.text[:180].replace("\n", " ")
        hint = ""
        if exc.response.status_code == 403:
            hint = " Upstream denied this request (possible anti-bot, IP policy, or geofence)."
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned HTTP {exc.response.status_code}. Body preview: {body_preview}.{hint}",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"Schema validation failed: {exc.errors()}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Upstream returned malformed JSON") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected proxy error: {type(exc).__name__}") from exc
PY

RUN cat > /app/index.html <<'HTML'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FastAPI JSON Proxy Bridge</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; background: #f6f8fa; }
      .container { max-width: 920px; margin: auto; }
      input, button { padding: 10px; font-size: 14px; }
      input { width: 100%; box-sizing: border-box; margin-bottom: 10px; }
      button { background: #0b5fff; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
      button:disabled { opacity: 0.6; cursor: not-allowed; }
      .status { margin-top: 10px; color: #555; }
      .error { margin-top: 10px; color: #b00020; font-weight: 600; white-space: pre-wrap; }
      .card { background: #fff; padding: 10px 12px; border-radius: 8px; margin-top: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
      .teams { font-weight: 700; }
      .meta { color: #555; font-size: 13px; }
    </style>
  </head>
  <body>
    <main class="container">
      <h1>Live Events Proxy</h1>
      <p>Frontend calls FastAPI (<code>/api/live-events</code>), FastAPI calls upstream JSON.</p>
      <input id="urlInput" value="https://www.sofascore.com/api/v1/sport/football/events/live" />
      <button id="loadBtn">Fetch Events</button>
      <p id="status" class="status"></p>
      <p id="error" class="error"></p>
      <section id="events"></section>
    </main>

    <script>
      const API_BASE = window.location.origin;
      const urlInput = document.getElementById('urlInput');
      const loadBtn = document.getElementById('loadBtn');
      const statusEl = document.getElementById('status');
      const errorEl = document.getElementById('error');
      const eventsEl = document.getElementById('events');

      function renderEvents(events) {
        eventsEl.innerHTML = '';
        if (!Array.isArray(events) || events.length === 0) {
          eventsEl.innerHTML = '<div class="card">No events returned.</div>';
          return;
        }

        events.forEach((event) => {
          const home = event?.homeTeam?.name || 'Home Team';
          const away = event?.awayTeam?.name || 'Away Team';
          const tournament = event?.tournament?.name || 'Unknown Tournament';
          const status = event?.status?.description || event?.status?.type || 'Unknown Status';

          const card = document.createElement('article');
          card.className = 'card';
          card.innerHTML = `
            <div class="teams">${home} vs ${away}</div>
            <div class="meta">Tournament: ${tournament}</div>
            <div class="meta">Status: ${status}</div>
            <div class="meta">ID: ${event?.id ?? 'N/A'}</div>
          `;
          eventsEl.appendChild(card);
        });
      }

      async function fetchEvents() {
        const target = urlInput.value.trim();
        errorEl.textContent = '';
        statusEl.textContent = 'Loading...';
        loadBtn.disabled = true;

        try {
          const response = await fetch(`${API_BASE}/api/live-events?target_url=${encodeURIComponent(target)}`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
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

          const count = Array.isArray(data.events) ? data.events.length : 0;
          statusEl.textContent = `Loaded ${count} event(s).`;
        } catch (err) {
          errorEl.textContent = `Failed to load events: ${err?.message || err}`;
          statusEl.textContent = '';
        } finally {
          loadBtn.disabled = false;
        }
      }

      loadBtn.addEventListener('click', fetchEvents);
    </script>
  </body>
</html>
HTML

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
