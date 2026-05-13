#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Convenience orchestrator — wires Algorithms 1 → 5 together.
#
# This is *the* script you run on a freshly-cloned lab.  It will:
#   1. Verify the target is reachable.
#   2. Run Algorithm 1 (discover endpoints).
#   3. Run Algorithm 2 (identify heavy endpoints).
#   4. Run Algorithms 3, 4 (HTTP/1.1 symmetric + asymmetric, Python variant).
#   5. Run the CURL variants of Algorithms 3, 4.
#   6. Run Algorithm 5 (HTTP/2 multiplexed attack, Go).
#   7. Sample target CPU/mem the whole time.
#
# Required env: docker compose stack from ./setup/ already running.
#
# Usage:
#   ./run_lab.sh [base_url] [reqs_per_client] [clients]
#
# Defaults: base_url=http://localhost:8080, reqs=500, clients=5  (gentle).
# For the full reproduction of Tables II-IX use:
#   ./run_lab.sh http://localhost:8080 2000 15
# -----------------------------------------------------------------------------
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS="${ROOT}/results"
mkdir -p "${RESULTS}"

BASE_URL="${1:-http://localhost:8080}"
REQS="${2:-500}"
CLIENTS="${3:-5}"

# Optional HTTPS endpoint for Algorithm 5.
H2_URL="${H2_URL:-${BASE_URL/http:/https:}}"
H2_URL="${H2_URL/:8080/:8443}"

# Optional container name to monitor target-side.
TARGET_CONTAINER="${TARGET_CONTAINER:-sockshop-gateway}"

echo "[run_lab] base_url=${BASE_URL}  H2=${H2_URL}"
echo "[run_lab] clients=${CLIENTS}  requests/client=${REQS}"
echo "[run_lab] results dir: ${RESULTS}"

# -- 0. reachability ----------------------------------------------------------
if ! curl -sS --max-time 5 -o /dev/null -w '%{http_code}\n' "${BASE_URL}/health" \
       | grep -qE '^(2|3)[0-9][0-9]$'; then
    echo "[!] gateway not reachable at ${BASE_URL}/health — run 'docker compose up -d' first" >&2
    exit 1
fi

# -- 1. Algorithm 1 -----------------------------------------------------------
echo "[run_lab] -- Algorithm 1: endpoint discovery --"
python3 "${ROOT}/algorithms/algorithm1_discover.py" \
    --oas "${BASE_URL}/v3/api-docs" \
    --client-root "${BASE_URL}/" \
    --out "${RESULTS}/endpoints.json"

# -- 2. Algorithm 2 -----------------------------------------------------------
echo "[run_lab] -- Algorithm 2: target identification --"
python3 "${ROOT}/algorithms/algorithm2_identify.py" \
    --endpoints "${RESULTS}/endpoints.json" \
    --base-url  "${BASE_URL}" \
    --api-key   "AX001-benign" \
    --top-n     5 \
    --out       "${RESULTS}/targets.json"

# -- (start target-side monitor in the background) ---------------------------
MON_CSV="${RESULTS}/monitor_$(date +%s).csv"
if docker ps --format '{{.Names}}' | grep -q "^${TARGET_CONTAINER}$"; then
    echo "[run_lab] monitoring container ${TARGET_CONTAINER} -> ${MON_CSV}"
    bash "${ROOT}/monitoring/monitor.sh" "${TARGET_CONTAINER}" "${MON_CSV}" 1 \
        >/dev/null 2>&1 &
    MON_PID=$!
    trap 'kill ${MON_PID} 2>/dev/null || true' EXIT
else
    echo "[run_lab] container ${TARGET_CONTAINER} not found; skipping target-side monitor"
fi

# -- 3. Algorithm 3 (Python) --------------------------------------------------
echo "[run_lab] -- Algorithm 3: HTTP/1.1 symmetric (httpx + multiprocessing) --"
python3 "${ROOT}/attacks/algorithm3_symmetric.py" \
    --target "${RESULTS}/targets.json" \
    --base-url "${BASE_URL}" \
    --clients "${CLIENTS}" \
    --requests "${REQS}" \
    --out "${RESULTS}/symmetric_py_$(date +%s).csv" \
    > "${RESULTS}/symmetric_py_summary.json" || true

# -- 4. Algorithm 3 (CURL) ----------------------------------------------------
echo "[run_lab] -- Algorithm 3: HTTP/1.1 symmetric (CURL) --"
bash "${ROOT}/attacks/algorithm3_symmetric.sh" \
    "${RESULTS}/targets.json" "${REQS}" "${CLIENTS}" || true

# -- 5. Algorithm 4 (Python) --------------------------------------------------
echo "[run_lab] -- Algorithm 4: HTTP/1.1 asymmetric (httpx + multiprocessing) --"
python3 "${ROOT}/attacks/algorithm4_asymmetric.py" \
    --target "${RESULTS}/targets.json" \
    --base-url "${BASE_URL}" \
    --clients "${CLIENTS}" \
    --requests "${REQS}" \
    --out "${RESULTS}/asymmetric_py_$(date +%s).csv" \
    > "${RESULTS}/asymmetric_py_summary.json" || true

# -- 6. Algorithm 4 (CURL) ----------------------------------------------------
echo "[run_lab] -- Algorithm 4: HTTP/1.1 asymmetric (CURL) --"
bash "${ROOT}/attacks/algorithm4_asymmetric.sh" \
    "${RESULTS}/targets.json" "${REQS}" "${CLIENTS}" || true

# -- 7. Algorithm 5 (Go / HTTP/2 multiplexed) --------------------------------
echo "[run_lab] -- Algorithm 5: HTTP/2 multiplexed attack (Go) --"
pushd "${ROOT}/attacks" > /dev/null
go run algorithm5_http2_mux.go \
    -target       "${H2_URL}" \
    -targets-file "${RESULTS}/targets.json" \
    -clients      "${CLIENTS}" \
    -requests     "${REQS}" \
    -streams      200 \
    -insecure || true
popd > /dev/null

# -- cleanup ------------------------------------------------------------------
if [[ -n "${MON_PID:-}" ]]; then
    sleep 2
    kill "${MON_PID}" 2>/dev/null || true
fi
echo "[run_lab] done. CSVs / JSON in ${RESULTS}/"
ls -1 "${RESULTS}/"
