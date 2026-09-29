#!/usr/bin/env bash
# Starts the backend (FastAPI on :8000) and the frontend dev server (Vite on :5173).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

missing=0
if ! command -v uv >/dev/null 2>&1; then
  echo "Missing: uv (Python package manager). Install with:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env"
  missing=1
fi
if ! command -v npm >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -lt 20 ]; then
  echo "Missing: Node.js 20+ (with npm). On Ubuntu:"
  echo "  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
  echo "  On macOS: brew install node"
  missing=1
fi
[ "$missing" -eq 0 ] || exit 1

EXTRAS="${VNFLOW_EXTRAS:---extra image --extra tagger}"
(cd "$ROOT/backend" && uv sync $EXTRAS)
(
  cd "$ROOT/frontend"
  # node_modules holds platform-specific binaries; reinstall if it was copied from another OS.
  platform="$(uname -sm)"
  if [ ! -x node_modules/.bin/vite ] || [ "$(cat node_modules/.vnflow-platform 2>/dev/null)" != "$platform" ]; then
    rm -rf node_modules
    npm install
    echo "$platform" > node_modules/.vnflow-platform
  fi
)

trap 'kill 0' EXIT
(cd "$ROOT/backend" && uv run uvicorn app.main:app --port 8000 --reload --reload-dir app) &
(cd "$ROOT/frontend" && npm run dev) &
wait
