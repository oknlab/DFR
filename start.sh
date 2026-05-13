#!/usr/bin/env bash
set -euo pipefail
redis-server --save '' --appendonly no --daemonize yes
exec ./web-data-os
