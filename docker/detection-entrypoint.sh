#!/bin/sh
# One detection container: API, watcher agent, and the platform UI (nginx).
set -eu

uvicorn api.main:app --host 127.0.0.1 --port 8000 &
python -m teleguard.agent --poll 5 -v --api-url http://127.0.0.1:8000 &
nginx -g "daemon off;"
