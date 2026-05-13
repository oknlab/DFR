FROM golang:1.24-alpine AS go_builder
WORKDIR /src
COPY go/main.go ./main.go
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags='-s -w' -o /out/go-fetch ./main.go

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends git redis-server && rm -rf /var/lib/apt/lists/*

# clone Firecrawl + Scrapling as requested
RUN git clone --depth 1 https://github.com/firecrawl/firecrawl /opt/firecrawl && \
    git clone --depth 1 https://github.com/D4Vinci/Scrapling /opt/Scrapling

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY --from=go_builder /out/go-fetch ./go-fetch
COPY start.sh ./start.sh
RUN chmod +x ./start.sh
EXPOSE 10000
CMD ["./start.sh"]
