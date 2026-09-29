#!/usr/bin/env bash
# Starts the backend (FastAPI on :8000) and the frontend dev server (Vite on :5173).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

EXTRAS="${VNFLOW_EXTRAS:---extra image --extra tagger}"
(cd "$ROOT/backend" && uv sync $EXTRAS)
(cd "$ROOT/frontend" && [ -d node_modules ] || npm install)

trap 'kill 0' EXIT
(cd "$ROOT/backend" && uv run uvicorn app.main:app --port 8000 --reload --reload-dir app) &
(cd "$ROOT/frontend" && npm run dev) &
wait
