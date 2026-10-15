#!/usr/bin/env bash
set -euo pipefail

uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000 &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM

cd frontend
npm run dev -- --host 127.0.0.1
