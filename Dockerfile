FROM golang:1.24-alpine AS builder
WORKDIR /src
COPY go/main.go ./main.go
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/web-data-os ./main.go

FROM debian:bookworm-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git redis-server redis-tools && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/firecrawl/firecrawl /opt/firecrawl && \
    git clone --depth 1 https://github.com/D4Vinci/Scrapling /opt/Scrapling
COPY --from=builder /out/web-data-os ./web-data-os
COPY start.sh ./start.sh
RUN chmod +x ./start.sh
EXPOSE 10000
CMD ["./start.sh"]
