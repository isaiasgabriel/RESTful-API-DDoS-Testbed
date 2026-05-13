#!/usr/bin/env python3
"""
Client-side monitor.

Independently of the attack workers, pings each target endpoint once per
second from a single thread and records the *user-perceived* latency, status
code, and any transport-level errors.  Use it during an attack to
demonstrate (a) latency spikes, (b) error-code transitions to 429/503/509/520,
and (c) full service unresponsiveness.

CSV columns:  timestamp,method,path,status,latency_ms,error

Usage:
    python3 monitor_client.py --target ../results/targets.json \\
        --out ../results/client_latency.csv \\
        --interval 1.0 --duration 300
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time

import httpx


OVERLOAD_CODES = {429, 503, 509, 520}


def main() -> int:
    ap = argparse.ArgumentParser(description="Client-side latency/error monitor")
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--duration", type=int, default=0,
                    help="Stop after N seconds. 0 = run until Ctrl-C.")
    ap.add_argument("--api-key", default="AX001-monitor",
                    help="X-API-KEY for the *monitor* (constant on purpose: "
                         "this client must not contribute to the attack).")
    ap.add_argument("--insecure", action="store_true")
    args = ap.parse_args()

    with open(args.target) as fh:
        doc = json.load(fh)
    base_url = args.base_url or doc.get("base_url")
    if not base_url:
        ap.error("base URL not supplied")

    targets = doc.get("target_list") or [
        {"method": e["method"], "path": e["path"]}
        for e in doc.get("all_endpoints", [])
    ]
    if not targets:
        ap.error("no targets in targets.json")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fh = open(args.out, "w", newline="")
    w = csv.writer(fh)
    w.writerow(["timestamp", "method", "path", "status", "latency_ms", "error"])

    end = time.time() + args.duration if args.duration > 0 else float("inf")
    headers = {
        "X-API-KEY": args.api_key,
        "User-Agent": "Algo-Monitor/1.0",
        "Accept": "application/json",
    }
    summary_buckets = {"2xx": 0, "4xx": 0, "5xx": 0,
                       "overload": 0, "errors": 0}

    print(f"[+] monitoring {len(targets)} target(s) every {args.interval}s "
          f"→ {args.out}", file=sys.stderr)

    try:
        with httpx.Client(base_url=base_url, verify=not args.insecure,
                          http2=False, timeout=15.0,
                          follow_redirects=False) as client:
            i = 0
            while time.time() < end:
                t = targets[i % len(targets)]
                i += 1
                m, p = t["method"].upper(), t["path"]
                status, err = -1, ""
                start = time.perf_counter()
                try:
                    r = client.request(m, p, headers=headers)
                    status = r.status_code
                except httpx.HTTPError as exc:
                    err = type(exc).__name__
                lat = (time.perf_counter() - start) * 1000
                w.writerow([int(time.time()), m, p, status,
                            round(lat, 2), err])
                fh.flush()

                if status == -1:
                    summary_buckets["errors"] += 1
                elif status in OVERLOAD_CODES:
                    summary_buckets["overload"] += 1
                elif 200 <= status < 300:
                    summary_buckets["2xx"] += 1
                elif 400 <= status < 500:
                    summary_buckets["4xx"] += 1
                elif 500 <= status < 600:
                    summary_buckets["5xx"] += 1

                sys.stderr.write(
                    f"\r{time.strftime('%H:%M:%S')} "
                    f"{m:6} {p[:40]:40} → {status:4}  "
                    f"{lat:7.1f} ms   "
                    f"[2xx={summary_buckets['2xx']} "
                    f"4xx={summary_buckets['4xx']} "
                    f"5xx={summary_buckets['5xx']} "
                    f"ovr={summary_buckets['overload']} "
                    f"err={summary_buckets['errors']}]"
                )
                sys.stderr.flush()
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        fh.close()
        print(f"\n[+] wrote {args.out}", file=sys.stderr)
        print(json.dumps(summary_buckets, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
