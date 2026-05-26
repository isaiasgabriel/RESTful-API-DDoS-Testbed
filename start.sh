#!/usr/bin/env bash
# Role: Start Sock Shop with a selectable API gateway plug-in via API_GATEWAY.
set -euo pipefail

# Usage:
#   API_GATEWAY=nginx ./start.sh
#   API_GATEWAY=kong REDIS_URL=redis://redis:6379 ./start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_COMPOSE="${SCRIPT_DIR}/gateways/base/docker-compose.yml"

gateway="${API_GATEWAY:-nginx}"
gateway_compose="${SCRIPT_DIR}/gateways/${gateway}/docker-compose.override.yml"

if [[ ! -f "${BASE_COMPOSE}" ]]; then
  echo "Error: base compose file not found at ${BASE_COMPOSE}" >&2
  exit 1
fi

if [[ ! -f "${gateway_compose}" ]]; then
  echo "Error: unsupported API_GATEWAY='${gateway}'." >&2
  echo "Supported values: kong, nginx" >&2
  exit 1
fi

extra_args=()
if [[ "${gateway}" == "kong" ]]; then
  if [[ -n "${REDIS_URL:-}" ]]; then
    if [[ "${REDIS_URL}" =~ ^redis://([^:/]+):([0-9]+)$ ]]; then
      export KONG_RATE_LIMIT_POLICY="redis"
      export KONG_REDIS_HOST="${BASH_REMATCH[1]}"
      export KONG_REDIS_PORT="${BASH_REMATCH[2]}"
      extra_args+=(--profile redis)
    else
      echo "Error: REDIS_URL must match redis://host:port (got '${REDIS_URL}')." >&2
      exit 1
    fi
  else
    export KONG_RATE_LIMIT_POLICY="local"
  fi
fi

echo "Starting Sock Shop with API gateway: ${gateway}"
docker compose \
  -f "${BASE_COMPOSE}" \
  -f "${gateway_compose}" \
  "${extra_args[@]}" \
  up -d
