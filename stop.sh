#!/usr/bin/env bash
# Role: Stop Sock Shop gateway plug-in stacks started via start.sh.
set -euo pipefail

# Usage:
#   ./stop.sh                  # auto-detect running gateway and stop it
#   API_GATEWAY=nginx ./stop.sh
#   ./stop.sh kong
#   ./stop.sh all              # stop all known gateway stack variants

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_COMPOSE="${SCRIPT_DIR}/gateways/base/docker-compose.yml"

list_gateways() {
  printf '%s\n' "${SCRIPT_DIR}"/gateways/*/docker-compose.override.yml \
    | xargs -n1 dirname | xargs -n1 basename | sort
}

down_gateway() {
  local gateway="$1"
  local gateway_compose="${SCRIPT_DIR}/gateways/${gateway}/docker-compose.override.yml"

  if [[ ! -f "${gateway_compose}" ]]; then
    echo "Skipping unknown gateway '${gateway}'." >&2
    return 0
  fi

  echo "Stopping Sock Shop stack for gateway: ${gateway}"
  docker compose \
    --project-directory "${SCRIPT_DIR}" \
    -f "${BASE_COMPOSE}" \
    -f "${gateway_compose}" \
    down -v --remove-orphans
}

detect_running_gateway() {
  local gateway
  for gateway in $(list_gateways); do
    local gateway_compose="${SCRIPT_DIR}/gateways/${gateway}/docker-compose.override.yml"
    local cid
    cid="$(docker compose \
      --project-directory "${SCRIPT_DIR}" \
      -f "${BASE_COMPOSE}" \
      -f "${gateway_compose}" \
      ps -q api-gateway 2>/dev/null || true)"
    if [[ -n "${cid}" ]]; then
      echo "${gateway}"
      return 0
    fi
  done
  return 1
}

requested_gateway="${1:-${API_GATEWAY:-}}"

if [[ -z "${requested_gateway}" ]]; then
  if detected_gateway="$(detect_running_gateway)"; then
    requested_gateway="${detected_gateway}"
    echo "Auto-detected running gateway: ${requested_gateway}"
  else
    supported_gateways="$(list_gateways | paste -sd ', ' -)"
    echo "No running gateway stack detected." >&2
    echo "Set API_GATEWAY or pass one argument. Supported values: ${supported_gateways}, all" >&2
    exit 1
  fi
fi

if [[ "${requested_gateway}" == "all" ]]; then
  for gateway in $(list_gateways); do
    down_gateway "${gateway}"
  done
  exit 0
fi

supported_csv="$(list_gateways | tr '\n' ',' | sed 's/,$//; s/,/, /g')"
if ! grep -qx "${requested_gateway}" < <(list_gateways); then
  echo "Error: unsupported API_GATEWAY='${requested_gateway}'." >&2
  echo "Supported values: ${supported_csv}, all" >&2
  exit 1
fi

down_gateway "${requested_gateway}"
