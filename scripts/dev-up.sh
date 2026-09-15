#!/usr/bin/env bash
# Start the local LINE adapter + a Cloudflare quick tunnel, and print the
# webhook URL to set in the LINE Developers Console.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN_DIR=".run"
mkdir -p "$RUN_DIR"

if lsof -ti:8000 >/dev/null 2>&1; then
  echo "Adapter already running on :8000."
else
  echo "==> Starting local adapter (uv run main.py)..."
  nohup uv run main.py > "$RUN_DIR/server.log" 2>&1 &
  sleep 2
fi

if [ -f "$RUN_DIR/tunnel.pid" ] && kill -0 "$(cat "$RUN_DIR/tunnel.pid")" 2>/dev/null; then
  echo "Tunnel already running (pid $(cat "$RUN_DIR/tunnel.pid"))."
else
  command -v cloudflared >/dev/null || {
    echo "cloudflared not found — install with: brew install cloudflared" >&2
    exit 1
  }
  echo "==> Starting Cloudflare tunnel..."
  nohup cloudflared tunnel --url http://localhost:8000 > "$RUN_DIR/tunnel.log" 2>&1 &
  echo $! > "$RUN_DIR/tunnel.pid"
  sleep 6
fi

URL=$(grep -Eo 'https://[a-zA-Z0-9.-]*trycloudflare\.com' "$RUN_DIR/tunnel.log" | head -1 || true)
echo ""
if [ -z "$URL" ]; then
  echo "Tunnel URL not ready yet — check $RUN_DIR/tunnel.log and re-run this script."
else
  echo "Webhook URL for the LINE Developers Console:"
  echo "  $URL/callback"
fi
