#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Target-side monitor.
#
# Samples CPU, memory and network statistics from a running Docker container
# (or a plain PID, see -p variant) once per second and appends a CSV.  Run it
# in a SECOND terminal alongside any of the attack scripts so you can later
# correlate "what the attacker sent" with "what the target experienced".
#
# Usage:
#   ./monitor.sh <container-name-or-id> [output.csv] [interval_seconds]
#
# Or, to monitor a PID instead of a container, set MONITOR_PID:
#   MONITOR_PID=12345 ./monitor.sh _ output.csv
#
# CSV columns:
#   timestamp,cpu_percent,mem_used_mb,mem_limit_mb,net_rx_bytes,net_tx_bytes,
#   blk_read_bytes,blk_write_bytes,pids
# -----------------------------------------------------------------------------
set -u
export LC_ALL=C

TARGET="${1:-}"
OUT="${2:-./monitor_$(date +%s).csv}"
INTERVAL="${3:-1}"

if [[ -z "$TARGET" && -z "${MONITOR_PID:-}" ]]; then
    echo "usage: $0 <container> [out.csv] [interval]   or   MONITOR_PID=... $0 _ out.csv" >&2
    exit 2
fi

echo "timestamp,cpu_percent,mem_used_mb,mem_limit_mb,net_rx_bytes,net_tx_bytes,blk_read_bytes,blk_write_bytes,pids" > "$OUT"
echo "[+] writing $OUT (Ctrl-C to stop, interval=${INTERVAL}s)" >&2

# Convert "123MiB" → "123" and "1.23GiB" → "1230" etc.
to_mb() {
    LC_ALL=C awk -v s="$1" 'BEGIN{
        v=s+0
        if (s ~ /GiB/) printf "%.2f", v*1024
        else if (s ~ /MiB/) printf "%.2f", v
        else if (s ~ /KiB/) printf "%.4f", v/1024
        else printf "%.2f", v/1048576
    }'
}
to_bytes() {
    LC_ALL=C awk -v s="$1" 'BEGIN{
        v=s+0
        if (s ~ /GB/) printf "%.0f", v*1e9
        else if (s ~ /MB/) printf "%.0f", v*1e6
        else if (s ~ /kB/ || s ~ /KB/) printf "%.0f", v*1e3
        else printf "%.0f", v
    }'
}

if [[ -n "${MONITOR_PID:-}" ]]; then
    PID="$MONITOR_PID"
    [[ -d /proc/$PID ]] || { echo "no such pid: $PID" >&2; exit 1; }
    while :; do
        if ! [[ -d /proc/$PID ]]; then
            echo "[!] pid $PID gone" >&2; break
        fi
        cpu=$(ps -p "$PID" -o %cpu= | tr -d ' ')
        mem=$(ps -p "$PID" -o rss=  | tr -d ' ') # KiB
        mem_mb=$(LC_ALL=C awk -v k="$mem" 'BEGIN{printf "%.2f", k/1024}')
        threads=$(ls /proc/$PID/task 2>/dev/null | wc -l)
        rx=$(awk '/eth0:|ens|enp/ {print $2; exit}' /proc/net/dev 2>/dev/null || echo 0)
        tx=$(awk '/eth0:|ens|enp/ {print $10; exit}' /proc/net/dev 2>/dev/null || echo 0)
        printf "%s,%s,%s,,%s,%s,,,%s\n" \
            "$(date +%s)" "$cpu" "$mem_mb" "$rx" "$tx" "$threads" >> "$OUT"
        sleep "$INTERVAL"
    done
    exit 0
fi

# Container mode (default).
command -v docker >/dev/null || { echo "docker required" >&2; exit 1; }

while :; do
    line=$(docker stats --no-stream --format \
        '{{.CPUPerc}};{{.MemUsage}};{{.NetIO}};{{.BlockIO}};{{.PIDs}}' "$TARGET" 2>/dev/null) \
        || { echo "[!] container $TARGET not running" >&2; break; }

    IFS=';' read -r cpu mem net blk pids <<< "$line"
    cpu="${cpu//%/}"; cpu="${cpu// /}"

    mem_used="${mem%/*}"; mem_lim="${mem#*/}"
    mem_used_mb=$(to_mb "$(echo "$mem_used" | tr -d ' ')")
    mem_lim_mb=$(to_mb  "$(echo "$mem_lim"  | tr -d ' ')")

    rx="${net%/*}"; tx="${net#*/}"
    rx_b=$(to_bytes "$(echo "$rx" | tr -d ' ')")
    tx_b=$(to_bytes "$(echo "$tx" | tr -d ' ')")

    r="${blk%/*}"; ww="${blk#*/}"
    r_b=$(to_bytes "$(echo "$r"  | tr -d ' ')")
    w_b=$(to_bytes "$(echo "$ww" | tr -d ' ')")

    printf "%s,%s,%s,%s,%s,%s,%s,%s,%s\n" \
        "$(date +%s)" "$cpu" "$mem_used_mb" "$mem_lim_mb" \
        "$rx_b" "$tx_b" "$r_b" "$w_b" "$pids" >> "$OUT"
    sleep "$INTERVAL"
done
