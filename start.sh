#!/usr/bin/env bash
# Role: Start Sock Shop with a selectable API gateway plug-in via API_GATEWAY.
set -euo pipefail

# Usage:
#   API_GATEWAY=nginx ./start.sh
#   API_GATEWAY=kong REDIS_URL=redis://redis:6379 ./start.sh
#   API_GATEWAY=envoy ./start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_COMPOSE="${SCRIPT_DIR}/gateways/base/docker-compose.yml"
TLS_KEY="${SCRIPT_DIR}/gateways/tls/key.pem"

gateway="${API_GATEWAY:-nginx}"
gateway_compose="${SCRIPT_DIR}/gateways/${gateway}/docker-compose.override.yml"

if [[ ! -f "${BASE_COMPOSE}" ]]; then
  echo "Error: base compose file not found at ${BASE_COMPOSE}" >&2
  exit 1
fi

if [[ ! -f "${gateway_compose}" ]]; then
  supported_gateways="$(printf '%s\n' "${SCRIPT_DIR}"/gateways/*/docker-compose.override.yml \
    | xargs -n1 dirname | xargs -n1 basename | sort | tr '\n' ',' | sed 's/,$//; s/,/, /g')"
  echo "Error: unsupported API_GATEWAY='${gateway}'." >&2
  echo "Supported values: ${supported_gateways}" >&2
  exit 1
fi

# Envoy runs as non-root in its container, so the mounted TLS key must be world-readable.
if [[ -f "${TLS_KEY}" ]]; then
  chmod 644 "${TLS_KEY}" || true
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
  --project-directory "${SCRIPT_DIR}" \
  -f "${BASE_COMPOSE}" \
  -f "${gateway_compose}" \
  "${extra_args[@]}" \
  up -d

echo "Gateway HTTP/1.1: http://localhost:8080"
echo "Gateway TLS/HTTP2: https://localhost:8443"
echo "Health check: curl -s http://localhost:8080/healthz"
