#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating venv at $VENV..."
  python3 -m venv "$VENV"
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

echo "Starting music-video-upscaler web UI on http://$HOST:$PORT"
exec "$PY" -m uvicorn web.server:app --host "$HOST" --port "$PORT"
