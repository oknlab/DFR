#!/usr/bin/env bash
set -euo pipefail
redis-server --save '' --appendonly no --daemonize yes
./go-fetch &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
