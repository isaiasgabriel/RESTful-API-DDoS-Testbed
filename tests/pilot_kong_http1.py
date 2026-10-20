#!/usr/bin/env python3
"""Bounded, sequential local pilot. Does not reset counters or remove containers.

Run on the Docker host: python3 tests/pilot_kong_http1.py
Requires Kong/Sock Shop already running on 127.0.0.1:8080.
Other traffic from the same identity invalidates the initial-state assumption.
"""
import csv
import datetime as dt
import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT, timeout=20)


def main():
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    out = ROOT / "results" / ("pilot-kong-http1-" + run_id)
    out.mkdir(parents=True)
    info = json.loads(docker("inspect", "sockshop-gateway"))[0]
    if info["Config"]["Image"] != "kong:3.7.1" or not info["State"]["Running"]:
        raise SystemExit("Expected running kong:3.7.1; no requests sent")
    config = docker("exec", "sockshop-gateway", "cat", "/kong.yml")
    (out / "kong.yml").write_text(config)
    for name, path in {
        "handler.lua": "/usr/local/share/lua/5.1/kong/plugins/rate-limiting/handler.lua",
        "policies.lua": "/usr/local/share/lua/5.1/kong/plugins/rate-limiting/policies/init.lua",
        "timestamp.lua": "/usr/local/share/lua/5.1/kong/tools/timestamp.lua",
    }.items():
        (out / name).write_text(docker("exec", "sockshop-gateway", "cat", path))
    metadata = {
        "run_id": run_id, "gateway_image": info["Config"]["Image"],
        "image_id": info["Image"], "container_id": info["Id"],
        "config_sha256": hashlib.sha256(config.encode()).hexdigest(),
        "protocol": "HTTP/1.1", "endpoint": "http://127.0.0.1:8080/catalogue",
        "requests_planned": 110, "pause_after_response_seconds": 0.1,
        "identity": "one host origin; no forwarded/auth identity headers",
        "initial_state": "new host UTC minute + 2 seconds; first remaining must be 99; assumes no competing traffic",
        "limitations": ["not HTTP/2", "backend receipt requires correlating frontend logs", "client timestamps are not gateway arrival timestamps", "resource samples are diagnostic, not saturation evidence"],
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2))
    # Wait before measurement, without consuming any quota through a health probe.
    start_at = (int(time.time()) // 60 + 1) * 60 + 2
    print(f"Artifacts: {out}\nWaiting {start_at - time.time():.1f}s for a fresh minute", flush=True)
    time.sleep(max(0, start_at - time.time()))
    since = dt.datetime.fromtimestamp(start_at - 2, dt.timezone.utc).isoformat()
    stop = threading.Event()

    def monitor():
        with (out / "resources.jsonl").open("w") as f:
            while not stop.is_set():
                stamp = time.time_ns()
                try:
                    raw = docker("stats", "--no-stream", "--format", "{{json .}}",
                                 "sockshop-gateway", "sockshop-frontend", "sockshop-catalogue", "sockshop-catalogue-db")
                    sample = {"collection_start_ns": stamp, "collection_end_ns": time.time_ns(),
                              "containers": [json.loads(line) for line in raw.splitlines() if line.strip()]}
                except (subprocess.SubprocessError, ValueError) as exc:
                    sample = {"collection_start_ns": stamp, "error": str(exc)}
                f.write(json.dumps(sample) + "\n")
                f.flush()
                stop.wait(1)

    worker = threading.Thread(target=monitor)
    worker.start()
    rows = []
    connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=10)
    fields = ["request_id", "send_ns", "receive_ns", "latency_ms", "status", "http_version",
              "remaining", "limit", "reset", "kong_request_id", "upstream_latency", "catalogue_valid", "error"]
    try:
        with (out / "requests.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for i in range(1, 111):
                request_id = f"{run_id}-{i:03d}"
                row = dict.fromkeys(fields, "")
                row.update(request_id=request_id, send_ns=time.time_ns())
                tick = time.perf_counter_ns()
                try:
                    connection.request("GET", f"/catalogue?pilot_id={request_id}", headers={"User-Agent": "tcc-kong-pilot/1.0"})
                    response = connection.getresponse()
                    body = response.read()
                    headers = dict((k.lower(), v) for k, v in response.getheaders())
                    (out / f"response-{i:03d}.json").write_text(json.dumps({"status": response.status, "headers": response.getheaders(), "body": body.decode("utf-8", errors="replace")}, indent=2))
                    valid = False
                    if response.status == 200:
                        data = json.loads(body)
                        valid = isinstance(data, list) and bool(data) and all(isinstance(x, dict) and "id" in x and "name" in x for x in data)
                    row.update(status=response.status, http_version=response.version,
                               remaining=headers.get("x-ratelimit-remaining-minute", ""),
                               limit=headers.get("x-ratelimit-limit-minute", ""),
                               reset=headers.get("ratelimit-reset", ""),
                               kong_request_id=headers.get("x-kong-request-id", ""),
                               upstream_latency=headers.get("x-kong-upstream-latency", ""), catalogue_valid=valid)
                except (OSError, http.client.HTTPException, ValueError) as exc:
                    row["error"] = str(exc)
                row.update(receive_ns=time.time_ns(), latency_ms=(time.perf_counter_ns() - tick) / 1e6)
                writer.writerow(row)
                f.flush()
                rows.append(row)
                if row["error"] or row["status"] not in (200, 429) or (row["status"] == 200 and not row["catalogue_valid"]):
                    print("Stopping on unhealthy response", flush=True)
                    break
                time.sleep(0.1)
    finally:
        connection.close()
        stop.set()
        worker.join(timeout=25)
        for container in ("sockshop-gateway", "sockshop-frontend", "sockshop-catalogue"):
            try:
                (out / f"{container}.log").write_text(docker("logs", "--since", since, "--timestamps", container))
            except subprocess.SubprocessError as exc:
                (out / f"{container}.log-error.txt").write_text(str(exc))
    counts = {str(status): sum(r["status"] == status for r in rows) for status in set(r["status"] for r in rows)}
    summary = {"requests_completed": len(rows), "status_counts": counts,
               "first_remaining": rows[0]["remaining"] if rows else None,
               "client_times_within_one_minute": bool(rows) and rows[0]["send_ns"] // 60_000_000_000 == rows[-1]["receive_ns"] // 60_000_000_000,
               "note": "Observed counts only; validate gateway logs and initial state before interpreting policy accuracy."}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    if len(rows) != 110 or any(r["error"] or r["status"] not in (200, 429) for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
