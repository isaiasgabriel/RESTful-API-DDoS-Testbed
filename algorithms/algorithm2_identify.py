#!/usr/bin/env python3
"""
Algorithm 2 — Identifying Target Endpoints.

Implementation of Algorithm 2 from Sivakumar & Thilagam (IJACSA 16/3, 2025).
The script:

  * Reads the unified endpoint list produced by `algorithm1_discover.py`.
  * Sends each endpoint a *valid* probe request (a single, lightweight call).
  * Records the response time and status code per call.
  * Classifies endpoints into:
        - High-latency / "computationally heavy" candidates (top-N by p95
          response time);
        - Error-prone candidates (those that return any of the
          status codes 429 / 503 / 509 / 520 — i.e. the gateway / origin
          reported overload conditions even under light, well-formed load).
  * Emits a JSON file consumable by Algorithms 3, 4, 5.

The script *probes politely*: defaults are 3 probes per endpoint, 250 ms
inter-request sleep, single thread.  This is target-identification, NOT the
attack — that is handled by algorithms 3+.

Usage
-----
    python3 algorithm2_identify.py \\
        --endpoints   ../results/endpoints.json \\
        --base-url    http://localhost:8080 \\
        --api-key     AX001-benign \\
        --probes      3 \\
        --top-n       5 \\
        --out         ../results/targets.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


# Status codes the paper calls out (Algorithm 2, lines 9-10 + §V.B) as
# overload / failure indicators worth scoring.
OVERLOAD_CODES = {429, 503, 509, 520}

# Endpoints we never want to "attack" in a lab (DB management, shutdown).
PATH_DENYLIST = (
    "/actuator", "/metrics", "/prometheus", "/shutdown", "/admin",
)


# ---------------------------------------------------------------------------
@dataclass
class ProbeResult:
    method: str
    path: str
    samples: list[float] = field(default_factory=list)
    statuses: list[int] = field(default_factory=list)
    errors: int = 0
    overload: int = 0

    @property
    def avg_ms(self) -> float:
        return statistics.fmean(self.samples) * 1000 if self.samples else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.samples:
            return 0.0
        s = sorted(self.samples)
        idx = max(0, int(0.95 * (len(s) - 1)))
        return s[idx] * 1000

    @property
    def max_ms(self) -> float:
        return max(self.samples) * 1000 if self.samples else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "avg_ms": round(self.avg_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "statuses": self.statuses,
            "errors": self.errors,
            "overload": self.overload,
        }


# ---------------------------------------------------------------------------
def _build_payload(method: str, params: list[dict]) -> tuple[str, dict, dict]:
    """Best-effort valid payload generation: fill required params with safe
    placeholder values that match their declared schema type."""
    query: dict[str, Any] = {}
    body: dict[str, Any] = {}
    path_subs: dict[str, str] = {}

    for p in params:
        loc = p.get("in", "query")
        typ = p.get("type", "string")
        if typ == "integer":
            v: Any = 1
        elif typ == "number":
            v = 1.0
        elif typ == "boolean":
            v = True
        else:
            v = "test"
        name = p.get("name", "")
        if not name:
            continue
        if loc == "path":
            path_subs[name] = str(v)
        elif loc == "query":
            query[name] = v
        elif loc in ("body", "formData"):
            body[name] = v

    return ("", query, body) if method == "GET" else ("", query, body)


def _resolve_path(path: str, subs: dict[str, str]) -> str:
    """Replace {placeholder} segments with provided substitutions, fall
    back to '1' for anything left so the URL is syntactically valid."""
    def _sub(match: "re.Match[str]") -> str:  # noqa: F821
        return subs.get(match.group(1), "1")

    import re
    return re.sub(r"\{([^}]+)\}", _sub, path)


def probe(client: httpx.Client, ep: dict, api_key: str,
          probes: int, sleep_s: float) -> ProbeResult:
    method = ep["method"].upper()
    path = ep["path"]
    params = ep.get("parameters", [])
    _, query, body = _build_payload(method, params)
    subs = {p["name"]: "1" for p in params if p.get("in") == "path"}
    full_path = _resolve_path(path, subs)

    headers = {
        "X-API-KEY": api_key,
        "User-Agent": "Algo2-Probe/1.0 (lab-only)",
        "Accept": "application/json",
    }
    result = ProbeResult(method=method, path=path)

    for _ in range(probes):
        try:
            start = time.perf_counter()
            r = client.request(
                method,
                full_path,
                params=query if method == "GET" else None,
                json=body if method != "GET" and body else None,
                headers=headers,
                timeout=15.0,
            )
            elapsed = time.perf_counter() - start
            result.samples.append(elapsed)
            result.statuses.append(r.status_code)
            if r.status_code in OVERLOAD_CODES:
                result.overload += 1
            elif r.status_code >= 500:
                result.errors += 1
        except httpx.HTTPError as exc:
            result.errors += 1
            result.statuses.append(-1)
            print(f"[probe] {method} {path}: {exc}", file=sys.stderr)
        time.sleep(sleep_s)
    return result


# ---------------------------------------------------------------------------
def select_targets(results: list[ProbeResult], top_n: int) -> dict:
    """Combine the two selection criteria from Algorithm 2 lines 15-16."""
    succeeded = [r for r in results if r.samples]
    by_p95 = sorted(succeeded, key=lambda r: r.p95_ms, reverse=True)
    heavy = by_p95[:top_n]
    error_prone = [r for r in results if r.overload or r.errors]

    target_keys = {(r.method, r.path) for r in heavy} | \
                  {(r.method, r.path) for r in error_prone}

    return {
        "heavy_by_latency": [r.as_dict() for r in heavy],
        "error_prone":      [r.as_dict() for r in error_prone],
        "target_list": [
            {"method": m, "path": p} for (m, p) in sorted(target_keys)
        ],
    }


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Algorithm 2 — identify computationally-heavy endpoints")
    ap.add_argument("--endpoints", required=True,
                    help="JSON produced by algorithm1_discover.py")
    ap.add_argument("--base-url", required=True,
                    help="Base URL of the gateway / target.")
    ap.add_argument("--api-key", default="AX001-benign",
                    help="X-API-KEY to use for probing.")
    ap.add_argument("--probes", type=int, default=3,
                    help="Probes per endpoint (default 3).")
    ap.add_argument("--sleep", type=float, default=0.25,
                    help="Seconds to wait between probes (default 0.25).")
    ap.add_argument("--top-n", type=int, default=5,
                    help="Top-N heaviest endpoints (default 5).")
    ap.add_argument("--out", required=True, help="Output JSON path.")
    args = ap.parse_args()

    with open(args.endpoints) as fh:
        endpoints = json.load(fh)

    endpoints = [e for e in endpoints
                 if not any(e["path"].startswith(d) for d in PATH_DENYLIST)]

    results: list[ProbeResult] = []
    with httpx.Client(base_url=args.base_url, http2=False,
                      verify=False, follow_redirects=True) as client:
        for i, ep in enumerate(endpoints, 1):
            print(f"[{i}/{len(endpoints)}] probing "
                  f"{ep['method']} {ep['path']}", file=sys.stderr)
            results.append(probe(client, ep, args.api_key,
                                 args.probes, args.sleep))

    payload = {
        "base_url": args.base_url,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "all_endpoints": [r.as_dict() for r in results],
        **select_targets(results, args.top_n),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)

    print(f"[done] {len(payload['target_list'])} target endpoints "
          f"-> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
