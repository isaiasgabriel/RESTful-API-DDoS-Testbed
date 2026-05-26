#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# High-resolution target-side monitor.
#
# Samples docker stats every 200ms (5 Hz) so brief CPU spikes from short
# attacks (e.g. Algorithm 5 finishing in ~2s) are visible.
#
# Usage:
#   ./monitor_fast.sh <container...>
#
# Output: prints a colorised CPU bar per container per sample, until Ctrl-C.
# -----------------------------------------------------------------------------
set -u
export LC_ALL=C

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <container> [container ...]" >&2
    echo "e.g.:  $0 sockshop-orders sockshop-gateway sockshop-carts" >&2
    exit 2
fi

CONTAINERS=("$@")

# We use `docker stats` in streaming mode and re-parse its output every
# 200ms via a Python helper (stable across docker-cli versions).
python3 - "$@" <<'PY'
import subprocess, sys, time, os, re

containers = sys.argv[1:]
fmt = "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"

# Use `docker stats --no-stream` repeatedly — cheap and predictable.
WIDTH = 60   # columns of the CPU bar
SAMPLE_HZ = 5
INTERVAL = 1.0 / SAMPLE_HZ

# ANSI helpers
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW= "\033[33m"
RED   = "\033[31m"
def color(pct):
    if pct < 50:  return GREEN
    if pct < 200: return YELLOW
    return RED

# Header
print("ts        ", "  ".join(f"{c:<24}" for c in containers))
print("-" * (10 + 28*len(containers)))

prev_lines = 0
try:
    while True:
        t0 = time.time()
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", fmt, *containers],
            capture_output=True, text=True, check=False,
        ).stdout
        rows = {}
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) < 3: continue
            name, cpu_s, mem = parts[0], parts[1], parts[2]
            try:
                cpu = float(cpu_s.rstrip("%"))
            except ValueError:
                cpu = 0.0
            rows[name] = (cpu, mem)

        ts = time.strftime("%H:%M:%S")
        cells = []
        for c in containers:
            cpu, mem = rows.get(c, (0.0, "-"))
            bar_len = min(WIDTH, int(cpu / 10))   # 10% per char, cap at 60 chars = 600%
            bar = color(cpu) + ("█"*bar_len).ljust(8) + RESET
            cells.append(f"{bar}{cpu:6.1f}%")
        print(ts, "  ".join(cells), flush=True)
        # Pad to ~INTERVAL
        sleep = INTERVAL - (time.time() - t0)
        if sleep > 0:
            time.sleep(sleep)
except KeyboardInterrupt:
    pass
PY
