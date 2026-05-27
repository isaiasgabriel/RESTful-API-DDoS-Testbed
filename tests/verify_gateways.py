#!/usr/bin/env python3
# Role: Run the gateway-agnostic equivalence verification pipeline for every plug-in.
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

from comparison_report import TEST_CASES, write_comparison  # noqa: E402

ROOT_DIR = TESTS_DIR.parent
RESULTS_DIR = TESTS_DIR / "results"
DEFAULT_EQUIVALENCE_GATEWAYS = ["kong", "nginx"]


def _run_pytest(gateway: str, verbose: bool) -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(TESTS_DIR / "test_rate_limiting.py"),
        "--gateway",
        gateway,
    ]
    if verbose:
        cmd.append("-v")
    return subprocess.run(cmd, cwd=ROOT_DIR).returncode


def verify_gateway(gateway: str, verbose: bool) -> int:
    print(f"\n{'=' * 60}")
    print(f"Verifying gateway: {gateway}")
    print(f"{'=' * 60}")
    print(f"  a. Start stack: API_GATEWAY={gateway} ./start.sh")
    print("  b–f. Liveness wait, pytest, report, tear down (via conftest session fixture)")
    return _run_pytest(gateway, verbose)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify all API gateway plug-ins with the same pytest suite.",
    )
    parser.add_argument(
        "--gateways",
        nargs="*",
        help="Gateways to verify (default: auto-discover under gateways/).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--skip-comparison",
        action="store_true",
        help="Only run per-gateway pytest; do not write comparison_report.json",
    )
    args = parser.parse_args()

    gateways = args.gateways or DEFAULT_EQUIVALENCE_GATEWAYS
    if not gateways:
        print("No gateway plug-ins found under gateways/", file=sys.stderr)
        return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    exit_codes: dict[str, int] = {}

    for gateway in gateways:
        exit_codes[gateway] = verify_gateway(gateway, args.verbose)

    if args.skip_comparison:
        return 1 if any(code != 0 for code in exit_codes.values()) else 0

    print("\nBuilding comparison report …")
    comparison = write_comparison(gateways, RESULTS_DIR)
    print(f"Wrote {RESULTS_DIR / 'comparison_report.json'}")
    print(f"Verdict: {comparison['verdict']}")
    if comparison["divergences"]:
        print("Divergences:")
        for item in comparison["divergences"]:
            print(f"  - {item}")

    print("\nPer-gateway pytest exit codes:")
    for gateway, code in exit_codes.items():
        print(f"  {gateway}: {code}")

    print("\nRequired test cases:", ", ".join(TEST_CASES))
    for gateway in gateways:
        report_path = RESULTS_DIR / f"{gateway}_report.json"
        if not report_path.is_file():
            print(f"  {gateway}: MISSING {report_path.name}")
            continue
        statuses = comparison["results"][gateway]
        summary = " ".join(f"{t}={statuses.get(t, '?')}" for t in TEST_CASES)
        print(f"  {gateway}: {summary}")

    if comparison["verdict"] == "divergent":
        return 1
    if any(code != 0 for code in exit_codes.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
