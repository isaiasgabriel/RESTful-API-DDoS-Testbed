#!/usr/bin/env python3
"""Validate saved sequential pilot evidence; never treats status != 429 as admission."""
import csv
import json
from pathlib import Path
import re
import sys
from collections import Counter


def analyze(path):
    rows = list(csv.DictReader((path / "requests.csv").open()))
    gateway = (path / "sockshop-gateway.log").read_text()
    frontend = (path / "sockshop-frontend.log").read_text()
    ids = [r["request_id"] for r in rows]
    gateway_ids = re.findall(r"pilot_id=([^\s\"]+)", gateway)
    frontend_ids = re.findall(r"pilot_id=([^\s\"]+)", frontend)
    matches = re.findall(r'(\S+) - - \[([^\]]+)\] "GET /catalogue\?pilot_id=([^\s]+) HTTP/1.1" (\d+)', gateway)
    ips = sorted(set(m[0] for m in matches))
    minutes = sorted(set(m[1].rsplit(":", 1)[0] for m in matches))
    frontend_counts = Counter(frontend_ids)
    checks = {
        "110_unique_requests": len(rows) == len(set(ids)) == 110,
        "all_http1_no_client_errors": all(r["http_version"] == "11" and not r["error"] for r in rows),
        "first_remaining_99": bool(rows) and rows[0]["remaining"] == "99",
        "configured_limit_100": all(r["limit"] == "100" for r in rows),
        "gateway_ids_exactly_once": Counter(gateway_ids) == Counter(ids),
        "gateway_status_matches_client": len(matches) == len(rows) and all(m[2] == r["request_id"] and m[3] == r["status"] for m, r in zip(matches, rows)),
        "one_gateway_ip_and_minute": len(ips) == len(minutes) == 1,
        "no_other_gateway_access": all('HTTP/' not in line or 'pilot_id=' in line for line in gateway.splitlines()),
        "successful_responses_have_catalogue": all(r["catalogue_valid"] == "True" for r in rows if r["status"] == "200"),
        "frontend_receipts_match_200": frontend_counts == Counter(r["request_id"] for r in rows if r["status"] == "200"),
        "only_200_or_429": all(r["status"] in ("200", "429") for r in rows),
    }
    # Reference is defined for this sequential trace, fresh fixed minute, quota 100.
    checks["remaining_sequence"] = all(r["remaining"] == str(max(99-i, 0)) for i, r in enumerate(rows))
    valid = all(checks.values())
    report = {"checks": checks, "evidence_consistent": valid, "observed_ip": ips,
              "gateway_minute": minutes, "frontend_receipts": len(frontend_ids),
              "status_counts": dict(Counter(r["status"] for r in rows)),
              "scope": "Single sequential HTTP/1.1 diagnostic pilot; not a final campaign or HTTP/2 result."}
    if valid:
        admitted = set(frontend_ids)
        excess = sum(r["request_id"] in admitted for r in rows[100:])
        false_positive = sum(r["status"] == "429" for r in rows[:100])
        report["pilot_metrics"] = {"excess_admissions": excess, "spillover_percent_of_quota": excess / 100 * 100,
                                   "false_positives": false_positive, "expected_admissions": 100,
                                   "false_positive_percent": false_positive / 100 * 100}
    samples = [json.loads(line) for line in (path / "resources.jsonl").read_text().splitlines()]
    with (path / "resources.csv").open("w", newline="") as f:
        fields = ["collection_start_ns", "collection_end_ns", "container", "cpu_percent", "memory_usage_raw"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            for container in sample.get("containers", []):
                writer.writerow({"collection_start_ns": sample["collection_start_ns"], "collection_end_ns": sample["collection_end_ns"],
                                 "container": container["Name"], "cpu_percent": container["CPUPerc"].rstrip("%"), "memory_usage_raw": container["MemUsage"]})
    report["resource_samples"] = len(samples)
    report["resource_errors"] = [s["error"] for s in samples if "error" in s]
    (path / "analysis.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return valid


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 tests/analyze_pilot_kong_http1.py results/pilot-kong-http1-RUN")
    raise SystemExit(0 if analyze(Path(sys.argv[1])) else 1)
