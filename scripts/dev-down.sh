#!/usr/bin/env bash
# Stop the local LINE adapter and Cloudflare tunnel started by dev-up.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

RUN_DIR=".run"

if lsof -ti:8000 >/dev/null 2>&1; then
  lsof -ti:8000 | xargs kill
  # Wait for the port to actually free up (uvicorn's reloader takes a
  # moment to die) so a follow-up dev-up.sh doesn't race this and think
  # the old, now-dead process is still serving.
  for _ in $(seq 1 20); do
    lsof -ti:8000 >/dev/null 2>&1 || break
    sleep 0.2
  done
  echo "Stopped local adapter (:8000)."
else
  echo "Local adapter not running."
fi

if [ -f "$RUN_DIR/tunnel.pid" ]; then
  pid=$(cat "$RUN_DIR/tunnel.pid")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "Stopped tunnel (pid $pid)."
  else
    echo "Tunnel not running."
  fi
  rm -f "$RUN_DIR/tunnel.pid"
else
  echo "Tunnel not running (no pidfile)."
fi
