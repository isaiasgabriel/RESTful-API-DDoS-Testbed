# Role: Build cross-gateway equivalence comparison from per-gateway pytest reports.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEST_CASES = [
    "test_under_limit",
    "test_over_limit",
    "test_retry_after",
    "test_limit_resets",
    "test_health_endpoint",
]


def discover_gateways(gateways_dir: Path) -> list[str]:
    names: list[str] = []
    for entry in sorted(gateways_dir.iterdir()):
        if not entry.is_dir() or entry.name == "base":
            continue
        if (entry / "docker-compose.override.yml").is_file():
            names.append(entry.name)
    return names


def load_gateway_report(results_dir: Path, gateway: str) -> dict[str, Any] | None:
    path = results_dir / f"{gateway}_report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _report_to_results(report: dict[str, Any]) -> dict[str, Any]:
    by_test: dict[str, dict[str, Any]] = {}
    for row in report.get("results", []):
        by_test[row["test"]] = {
            "status": "pass" if row["status"] == "passed" else row["status"],
            "p50_ms": row.get("latency_p50_ms"),
            "p95_ms": row.get("latency_p95_ms"),
        }

    results: dict[str, Any] = {}
    for test_name in TEST_CASES:
        entry = by_test.get(test_name, {"status": "missing", "p50_ms": None, "p95_ms": None})
        results[test_name] = entry["status"]
        results[f"{test_name}__p50_ms"] = entry["p50_ms"]
        results[f"{test_name}__p95_ms"] = entry["p95_ms"]
    return results


def build_comparison(
    gateways: list[str],
    results_dir: Path,
) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    divergences: list[str] = []

    for gateway in gateways:
        report = load_gateway_report(results_dir, gateway)
        if report is None:
            results[gateway] = {test: "missing" for test in TEST_CASES}
            divergences.append(f"{gateway}: tests/results/{gateway}_report.json not found")
            continue
        results[gateway] = _report_to_results(report)

    for test_name in TEST_CASES:
        statuses = {gw: results[gw].get(test_name) for gw in gateways}
        if len(set(statuses.values())) != 1 or statuses[gateways[0]] != "pass":
            divergences.append(
                f"{test_name}: " + ", ".join(f"{gw}={statuses[gw]}" for gw in gateways)
            )

    verdict = "equivalent" if not divergences else "divergent"

    return {
        "gateways": gateways,
        "test_cases": TEST_CASES,
        "results": results,
        "verdict": verdict,
        "divergences": divergences,
    }


def write_comparison(
    gateways: list[str],
    results_dir: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    payload = build_comparison(gateways, results_dir)
    out = output_path or (results_dir / "comparison_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
