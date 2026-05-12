#!/usr/bin/env bash
# Tiny helper: hit the agent-server health endpoint and pretty-print.
# Defaults assume `npm run dev:dangerously-dockerless` from agent-canvas.
# Override with: AGENT_SERVER=http://127.0.0.1:8000 ./health.sh

set -euo pipefail

AGENT_SERVER="${AGENT_SERVER:-http://127.0.0.1:18000}"

response="$(curl -fsS "${AGENT_SERVER}/health")"

if command -v jq >/dev/null 2>&1; then
  printf '%s\n' "${response}" | jq .
else
  echo "jq not installed; falling back to raw curl"
  printf '%s\n' "${response}"
fi
