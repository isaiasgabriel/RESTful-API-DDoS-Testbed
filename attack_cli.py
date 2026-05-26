#!/usr/bin/env python3
"""
Interactive launcher for lab/attacks scripts.

Select an attack from a numbered menu (or pass --attack) and run it with
defaults from README.md / run_lab.sh.

⚠️  Lab use only — authorized targets only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parent
ATTACKS_DIR = LAB_ROOT / "attacks"
RESULTS_DIR = LAB_ROOT / "results"
DEFAULT_TARGETS = RESULTS_DIR / "targets.json"


@dataclass(frozen=True)
class AttackSpec:
    key: str
    title: str
    description: str
    needs_go: bool = False
    needs_jq: bool = False


ATTACKS: tuple[AttackSpec, ...] = (
    AttackSpec(
        "3-py",
        "Algorithm 3 — Symmetric HTTP/1.1 (Python)",
        "httpx + multiprocessing; same heavy endpoint per request.",
    ),
    AttackSpec(
        "3-sh",
        "Algorithm 3 — Symmetric HTTP/1.1 (CURL)",
        "Bash/curl variant from the paper (§VI.C.2).",
        needs_jq=True,
    ),
    AttackSpec(
        "4-py",
        "Algorithm 4 — Asymmetric HTTP/1.1 (Python)",
        "Rotates across heavy endpoints with path/query mutation.",
    ),
    AttackSpec(
        "4-sh",
        "Algorithm 4 — Asymmetric HTTP/1.1 (CURL)",
        "Bash/curl asymmetric variant.",
        needs_jq=True,
    ),
    AttackSpec(
        "5-go",
        "Algorithm 5 — HTTP/2 multiplexed (Go)",
        "Many streams per TCP connection against HTTPS :8443.",
        needs_go=True,
    ),
)

ATTACK_BY_KEY = {a.key: a for a in ATTACKS}


def _http_to_https_h2(base_url: str) -> str:
    url = base_url.replace("http://", "https://", 1)
    if ":8080" in url:
        url = url.replace(":8080", ":8443", 1)
    return url


def _check_health(base_url: str) -> bool:
    import urllib.error
    import urllib.request

    url = f"{base_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _require_targets(path: Path) -> None:
    if not path.is_file():
        sys.exit(
            f"[!] targets file not found: {path}\n"
            "    Run Algorithm 1 and 2 first (see README.md Quick start)."
        )
    try:
        json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"[!] invalid JSON in {path}: {exc}")


def _timestamped_csv(prefix: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR / f"{prefix}_{int(time.time())}.csv"


def _build_command(
    key: str,
    *,
    targets: Path,
    base_url: str,
    clients: int,
    requests: int,
    streams: int,
    insecure: bool,
) -> list[str]:
    targets = targets.resolve()
    out_csv = _timestamped_csv(
        {
            "3-py": "symmetric",
            "4-py": "asymmetric",
            "5-go": "h2mux",
        }.get(key, "")
    )

    if key == "3-py":
        cmd = [
            sys.executable,
            str(ATTACKS_DIR / "algorithm3_symmetric.py"),
            "--target", str(targets),
            "--base-url", base_url,
            "--clients", str(clients),
            "--requests", str(requests),
            "--out", str(out_csv),
        ]
        if insecure:
            cmd.append("--insecure")
        return cmd

    if key == "3-sh":
        script = ATTACKS_DIR / "algorithm3_symmetric.sh"
        return ["bash", str(script), str(targets), str(requests), str(clients)]

    if key == "4-py":
        cmd = [
            sys.executable,
            str(ATTACKS_DIR / "algorithm4_asymmetric.py"),
            "--target", str(targets),
            "--base-url", base_url,
            "--clients", str(clients),
            "--requests", str(requests),
            "--out", str(out_csv),
        ]
        if insecure:
            cmd.append("--insecure")
        return cmd

    if key == "4-sh":
        script = ATTACKS_DIR / "algorithm4_asymmetric.sh"
        return ["bash", str(script), str(targets), str(requests), str(clients)]

    if key == "5-go":
        h2_url = os.environ.get("H2_URL") or _http_to_https_h2(base_url)
        cmd = [
            "go", "run", "algorithm5_http2_mux.go",
            "-target", h2_url,
            "-targets-file", str(targets),
            "-clients", str(clients),
            "-requests", str(requests),
            "-streams", str(streams),
        ]
        if insecure:
            cmd.append("-insecure")
        cmd.extend(["-out", str(out_csv)])
        return cmd

    raise ValueError(f"unknown attack key: {key}")


def _cwd_for(key: str) -> Path | None:
    return ATTACKS_DIR if key == "5-go" else None


def _preflight(spec: AttackSpec) -> None:
    if spec.needs_go and not shutil.which("go"):
        sys.exit("[!] 'go' not found on PATH (required for Algorithm 5).")
    if spec.needs_jq and not shutil.which("jq"):
        sys.exit("[!] 'jq' not found on PATH (required for CURL variants).")
    if spec.key.endswith("-sh") and not shutil.which("curl"):
        sys.exit("[!] 'curl' not found on PATH (required for CURL variants).")


def _print_menu() -> None:
    print("\n  RESTful API DDoS Lab — Attack Launcher")
    print("  ⚠️  Authorized lab targets only.\n")
    for i, spec in enumerate(ATTACKS, start=1):
        print(f"  [{i}] {spec.title}")
        print(f"      {spec.description}")
    print("\n  [0] Exit\n")


def _resolve_attack_key(choice: str) -> str | None:
    choice = choice.strip()
    if choice in ("0", "q", "quit", "exit"):
        return None
    if choice in ATTACK_BY_KEY:
        return choice
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(ATTACKS):
            return ATTACKS[idx - 1].key
    return None


def _interactive_select() -> str | None:
    _print_menu()
    try:
        raw = input("Select attack [0-{}]: ".format(len(ATTACKS)))
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return _resolve_attack_key(raw)


def _list_attacks() -> None:
    for i, spec in enumerate(ATTACKS, start=1):
        print(f"{i:2}  {spec.key:6}  {spec.title}")


def _run_attack(key: str, args: argparse.Namespace) -> int:
    spec = ATTACK_BY_KEY.get(key)
    if spec is None:
        sys.exit(f"[!] unknown attack key '{key}'. Use --list for options.")

    targets = Path(args.targets)
    _require_targets(targets)
    _preflight(spec)

    base_url = args.base_url
    if not args.skip_health_check and not _check_health(base_url):
        print(
            f"[!] gateway not reachable at {base_url}/health\n"
            "    Start the lab: cd setup && docker compose up -d\n"
            "    Or pass --skip-health-check to run anyway.",
            file=sys.stderr,
        )
        return 1

    cmd = _build_command(
        key,
        targets=targets,
        base_url=base_url,
        clients=args.clients,
        requests=args.requests,
        streams=args.streams,
        insecure=args.insecure,
    )
    cwd = _cwd_for(key)

    print(f"\n[*] {spec.title}")
    print(f"[*] command: {' '.join(cmd)}")
    if cwd:
        print(f"[*] cwd: {cwd}")
    print()

    proc = subprocess.run(cmd, cwd=cwd)
    return proc.returncode


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    keys = ", ".join(a.key for a in ATTACKS)
    ap = argparse.ArgumentParser(
        description="Launch lab attacks from attacks/ with a simple menu.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--attack", "-a", metavar="KEY",
        help=f"Attack to run without menu ({keys}).",
    )
    ap.add_argument("--list", action="store_true", help="List attacks and exit.")
    ap.add_argument(
        "--targets", type=Path, default=DEFAULT_TARGETS,
        help="targets.json from Algorithm 2.",
    )
    ap.add_argument(
        "--base-url", default="http://localhost:8080",
        help="Gateway base URL (HTTP); Algorithm 5 uses HTTPS :8443.",
    )
    ap.add_argument("--clients", type=int, default=15,
                     help="Parallel attacker workers/processes.")
    ap.add_argument("--requests", type=int, default=2000,
                     help="Requests per worker (per README defaults).")
    ap.add_argument("--streams", type=int, default=200,
                     help="Algorithm 5: max in-flight HTTP/2 streams per worker.")
    ap.add_argument(
        "--insecure", action="store_true", default=True,
        help="Skip TLS verification for HTTPS (default: on for lab certs).",
    )
    ap.add_argument(
        "--secure", action="store_true",
        help="Verify TLS certificates (disables default --insecure).",
    )
    ap.add_argument(
        "--skip-health-check", action="store_true",
        help="Do not probe /health before launching.",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.secure:
        args.insecure = False

    if args.list:
        _list_attacks()
        return 0

    key = args.attack
    if key is None:
        key = _interactive_select()
        if key is None:
            print("Cancelled.")
            return 0

    return _run_attack(key, args)


if __name__ == "__main__":
    raise SystemExit(main())
