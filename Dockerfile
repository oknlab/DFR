# ─── OKNLAB Search Engine ───────────────────────────────────────────────────
# Built by OKNLAB
# Private, ad-free, no tracking search engine
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

# Labels
LABEL maintainer="OKNLAB"
LABEL description="OKNLAB Search Engine - Private, Ad-Free, No Tracking"
LABEL version="1.0.0"

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REDIS_URL=redis://redis:6379/0 \
    CACHE_TTL=300

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r oknlab && \
    useradd -r -g oknlab -d /app -s /sbin/nologin oknlab

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi==0.115.6 \
    uvicorn[standard]==0.34.0 \
    httpx==0.28.1 \
    redis[hiredis]==5.2.1 \
    beautifulsoup4==4.12.3 \
    lxml==5.3.0

# Copy application files
COPY main.py web_search.py ui.html ./

# Set ownership
RUN chown -R oknlab:oknlab /app

# Switch to non-root user
USER oknlab

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--access-log", \
     "--log-level", "warning", \
     "--server-header", \
     "--proxy-headers"]
