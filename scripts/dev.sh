#!/usr/bin/env bash
# Local development without Docker: backend with auto-reload + frontend dev server.
# Requires Python 3.11+ and Node 20+. Postgres/Redis/Qdrant are optional locally
# (the backend degrades gracefully), but for full behaviour run: docker compose up postgres redis qdrant
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

(
  cd "$ROOT/backend"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements-dev.txt
  fi
  DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./dev.db}" \
    .venv/bin/uvicorn main:app --reload --port 8000
) &

(
  cd "$ROOT/frontend"
  [ -d node_modules ] || npm install
  npm run dev
) &

wait
