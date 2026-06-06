# ─── OKNLAB Search Engine ───────────────────────────────────────────────────
# Built by OKNLAB
# Private, ad-free, no tracking search engine
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

LABEL maintainer="OKNLAB"
LABEL description="OKNLAB Search Engine - Private, Ad-Free, No Tracking"
LABEL version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REDIS_URL=redis://redis:6379/0 \
    CACHE_TTL=300

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r oknlab && \
    useradd -r -g oknlab -d /app -s /sbin/nologin oknlab

WORKDIR /app

# Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application files
COPY main.py web_search.py ui.html ./

RUN chown -R oknlab:oknlab /app
USER oknlab

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "warning", \
     "--proxy-headers"]
