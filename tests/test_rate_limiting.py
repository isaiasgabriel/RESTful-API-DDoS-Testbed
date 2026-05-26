# Role: End-to-end gateway-agnostic rate-limiting tests for Sock Shop.
from __future__ import annotations

import json
import time

import httpx

BASE_URL = "http://127.0.0.1:8080"
HTTPS_BASE_URL = "https://127.0.0.1:8443"


def _send_requests(count: int, path: str = "/") -> tuple[list[int], list[float], list[httpx.Response]]:
    statuses: list[int] = []
    latencies_ms: list[float] = []
    responses: list[httpx.Response] = []
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        for _ in range(count):
            start = time.perf_counter()
            response = client.get(path)
            latencies_ms.append((time.perf_counter() - start) * 1000.0)
            statuses.append(response.status_code)
            responses.append(response)
    return statuses, latencies_ms, responses


def test_under_limit(record_latencies) -> None:
    statuses, latencies_ms, _ = _send_requests(90, "/")
    record_latencies(latencies_ms)
    assert all(code != 429 for code in statuses)


def test_over_limit(record_latencies) -> None:
    statuses, latencies_ms, _ = _send_requests(150, "/")
    record_latencies(latencies_ms)
    assert any(code == 429 for code in statuses)


def test_retry_after(record_latencies) -> None:
    statuses, latencies_ms, responses = _send_requests(150, "/")
    record_latencies(latencies_ms)

    retry_response = next((r for r in responses if r.status_code == 429), None)
    assert retry_response is not None, f"No 429 response seen in statuses={statuses}"
    assert "Retry-After" in retry_response.headers


def test_limit_resets(record_latencies) -> None:
    warm_statuses, warm_latencies_ms, _ = _send_requests(150, "/")
    record_latencies(warm_latencies_ms)
    assert any(code == 429 for code in warm_statuses)

    time.sleep(61)

    reset_statuses, reset_latencies_ms, _ = _send_requests(10, "/")
    record_latencies(reset_latencies_ms)
    assert all(code != 429 for code in reset_statuses)


def test_health_endpoint(record_latencies) -> None:
    start = time.perf_counter()
    response = httpx.get(f"{BASE_URL}/healthz", timeout=5.0)
    latency_ms = (time.perf_counter() - start) * 1000.0
    record_latencies([latency_ms])

    assert response.status_code == 200
    if response.text.strip():
        json.loads(response.text)
