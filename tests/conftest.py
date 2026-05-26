# Role: Shared pytest fixtures/options for gateway stack lifecycle and test reporting.
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
BASE_COMPOSE = ROOT_DIR / "gateways" / "base" / "docker-compose.yml"
RESULTS_DIR = ROOT_DIR / "tests" / "results"
HEALTH_URL = "http://127.0.0.1:8080/healthz"

LATENCIES_BY_TEST: dict[str, list[float]] = {}
OUTCOME_BY_TEST: dict[str, str] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--gateway",
        action="store",
        default="nginx",
        choices=["kong", "nginx"],
        help="Gateway plug-in under test.",
    )


def _compose_base_cmd(gateway: str) -> list[str]:
    override = ROOT_DIR / "gateways" / gateway / "docker-compose.override.yml"
    return [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT_DIR),
        "-f",
        str(BASE_COMPOSE),
        "-f",
        str(override),
    ]


def _wait_for_health(deadline_seconds: int = 30) -> None:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(HEALTH_URL, timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise RuntimeError("Gateway did not become healthy on /healthz within 30 seconds.")


@pytest.fixture(scope="session")
def gateway_name(pytestconfig: pytest.Config) -> str:
    return str(pytestconfig.getoption("--gateway"))


@pytest.fixture(scope="session", autouse=True)
def stack_lifecycle(gateway_name: str) -> None:
    env = os.environ.copy()
    env["API_GATEWAY"] = gateway_name

    subprocess.run(["bash", "start.sh"], cwd=ROOT_DIR, env=env, check=True)
    _wait_for_health()
    yield

    down_cmd = _compose_base_cmd(gateway_name) + ["down", "-v", "--remove-orphans"]
    subprocess.run(down_cmd, cwd=ROOT_DIR, env=env, check=True)


@pytest.fixture
def record_latencies(request: pytest.FixtureRequest):
    test_name = request.node.name

    def _record(latencies_ms: list[float]) -> None:
        LATENCIES_BY_TEST.setdefault(test_name, []).extend(latencies_ms)

    return _record


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        OUTCOME_BY_TEST[item.name] = report.outcome


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * percentile
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    gateway = str(session.config.getoption("--gateway"))
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for test_name in sorted(OUTCOME_BY_TEST):
        latencies = LATENCIES_BY_TEST.get(test_name, [])
        rows.append(
            {
                "gateway": gateway,
                "test": test_name,
                "status": OUTCOME_BY_TEST[test_name],
                "latency_p50_ms": _percentile(latencies, 0.50),
                "latency_p95_ms": _percentile(latencies, 0.95),
            }
        )

    report_path = RESULTS_DIR / f"{gateway}_report.json"
    report_payload = {"gateway": gateway, "exitstatus": exitstatus, "results": rows}
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    header = f"{'gateway':<10} {'test':<24} {'status':<8} {'p50(ms)':>10} {'p95(ms)':>10}"
    print("\nRate-limit test summary")
    print(header)
    print("-" * len(header))
    for row in rows:
        p50 = "n/a" if row["latency_p50_ms"] is None else f"{row['latency_p50_ms']:.2f}"
        p95 = "n/a" if row["latency_p95_ms"] is None else f"{row['latency_p95_ms']:.2f}"
        print(f"{row['gateway']:<10} {row['test']:<24} {row['status']:<8} {p50:>10} {p95:>10}")
