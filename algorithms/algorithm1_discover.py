#!/usr/bin/env python3
"""
Algorithm 1 — Discovering Endpoints.

Faithful implementation of Algorithm 1 from Sivakumar & Thilagam (IJACSA 16/3,
2025). Builds a unified endpoint list by:

    1. Parsing one or more OpenAPI Specification (OAS) documents (v2 or v3,
       JSON or YAML, local file or remote URL).
    2. Crawling client-side code (HTML, JS bundles) reachable from the front-
       end and extracting URL/route literals via regular-expression mining.
    3. Optionally consuming a "manual" hint file (e.g. routes extracted by
       Diggy from an APK).
    4. De-duplicating (METHOD, PATH) pairs and emitting a single JSON file
       that downstream algorithms (Algorithm 2…5) consume.

Usage
-----
    python3 algorithm1_discover.py \\
        --oas      http://localhost:8080/v3/api-docs \\
        --oas      ./swagger-user.yaml \\
        --client-root http://localhost:8080/ \\
        --extra-routes ./apk-routes.txt \\
        --out      ../results/endpoints.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    source: str
    parameters: tuple = field(default_factory=tuple)  # ((name, in, required, type), ...)
    consumes: str = ""
    produces: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["parameters"] = [
            {"name": n, "in": loc, "required": req, "type": typ}
            for (n, loc, req, typ) in self.parameters
        ]
        return d


# ---------------------------------------------------------------------------
# OAS parsing
# ---------------------------------------------------------------------------
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _load_oas(src: str) -> dict:
    """Load OAS from a URL or a local file (JSON or YAML)."""
    if src.startswith(("http://", "https://")):
        r = requests.get(src, timeout=15, verify=False)
        r.raise_for_status()
        text = r.text
    else:
        with open(src, "r", encoding="utf-8") as fh:
            text = fh.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return yaml.safe_load(text)


def parse_oas(src: str) -> list[Endpoint]:
    spec = _load_oas(src)
    base_path = spec.get("basePath", "") or ""
    endpoints: list[Endpoint] = []
    for raw_path, item in (spec.get("paths") or {}).items():
        full = base_path.rstrip("/") + "/" + raw_path.lstrip("/")
        full = re.sub(r"/+", "/", full)
        common_params = item.get("parameters", []) or []
        for verb, op in item.items():
            if verb.lower() not in HTTP_METHODS:
                continue
            params = list(common_params) + list(op.get("parameters", []) or [])
            param_tuple = tuple(
                (
                    p.get("name", ""),
                    p.get("in", ""),
                    bool(p.get("required", False)),
                    (p.get("schema") or {}).get("type", p.get("type", "string")),
                )
                for p in params
            )
            endpoints.append(
                Endpoint(
                    method=verb.upper(),
                    path=full,
                    source=f"oas:{src}",
                    parameters=param_tuple,
                    consumes=",".join(op.get("consumes", []) or []),
                    produces=",".join(op.get("produces", []) or []),
                )
            )
    return endpoints


# ---------------------------------------------------------------------------
# Client-side code scraping
# ---------------------------------------------------------------------------
# Regexes inspired by tools such as `LinkFinder` / `JSluice`.  We keep them
# intentionally generic so we recover routes from raw JS bundles and inline
# fetch()/axios()/$.ajax() call sites.
URL_LITERAL_RE = re.compile(
    r"""['"`]
        (
            (?:\\/|\/)                # leading slash
            [A-Za-z0-9_\-\/.{}:?=&%]+ # path-ish chars (allow path params)
        )
        ['"`]
    """,
    re.VERBOSE,
)
FETCH_VERB_RE = re.compile(
    r"""(?:fetch|axios|http|request|ajax)\s*\(\s*
        \{[^}]*?
        method\s*:\s*['"`](?P<method>GET|POST|PUT|PATCH|DELETE)['"`][^}]*?
        url\s*:\s*['"`](?P<url>[^'"`]+)['"`]
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)
AXIOS_VERB_RE = re.compile(
    r"""axios\.(?P<method>get|post|put|patch|delete)\s*\(\s*
        ['"`](?P<url>[^'"`]+)['"`]
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _looks_like_route(s: str) -> bool:
    if len(s) > 200 or " " in s:
        return False
    if s.startswith(("//", "data:", "javascript:")):
        return False
    if not s.startswith("/"):
        return False
    if any(s.endswith(ext) for ext in (".css", ".png", ".jpg", ".jpeg", ".gif",
                                       ".svg", ".ico", ".woff", ".woff2",
                                       ".ttf", ".map", ".js")):
        return False
    return True


def _fetch(url: str) -> str:
    try:
        r = requests.get(url, timeout=10, verify=False)
        if r.status_code < 400 and r.text:
            return r.text
    except requests.RequestException:
        pass
    return ""


def crawl_client(root: str, max_assets: int = 50) -> list[Endpoint]:
    """Fetch the front-end root, walk its <script src> assets, scrape paths."""
    out: list[Endpoint] = []
    html = _fetch(root)
    if not html:
        return out

    soup = BeautifulSoup(html, "lxml")
    assets: set[str] = {root}
    for tag in soup.find_all(["script", "link"]):
        ref = tag.get("src") or tag.get("href")
        if ref:
            assets.add(urljoin(root, ref))
        if len(assets) >= max_assets:
            break

    for asset in assets:
        body = html if asset == root else _fetch(asset)
        if not body:
            continue

        # Generic URL literals → assume GET unless they appear inside a
        # fetch()/axios() call site (handled below).
        for m in URL_LITERAL_RE.finditer(body):
            path = m.group(1).replace("\\/", "/")
            if _looks_like_route(path):
                out.append(Endpoint("GET", path, f"client:{asset}"))

        # fetch({method, url}) call sites
        for m in FETCH_VERB_RE.finditer(body):
            path = urlparse(m.group("url")).path or m.group("url")
            if _looks_like_route(path):
                out.append(Endpoint(m.group("method").upper(), path,
                                    f"client:{asset}"))

        # axios.get('/foo')
        for m in AXIOS_VERB_RE.finditer(body):
            path = urlparse(m.group("url")).path or m.group("url")
            if _looks_like_route(path):
                out.append(Endpoint(m.group("method").upper(), path,
                                    f"client:{asset}"))
    return out


# ---------------------------------------------------------------------------
# Extra hints (e.g. routes from a reverse-engineered APK)
# ---------------------------------------------------------------------------
EXTRA_LINE_RE = re.compile(r"^\s*(GET|POST|PUT|PATCH|DELETE)?\s*(\S+)\s*$",
                           re.IGNORECASE)


def parse_extra(path: str) -> list[Endpoint]:
    out: list[Endpoint] = []
    if not path or not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = EXTRA_LINE_RE.match(line)
            if not m:
                continue
            verb = (m.group(1) or "GET").upper()
            url = m.group(2)
            p = urlparse(url).path or url
            if _looks_like_route(p):
                out.append(Endpoint(verb, p, f"extra:{path}"))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _dedupe(endpoints: Iterable[Endpoint]) -> list[Endpoint]:
    seen: dict[tuple[str, str], Endpoint] = {}
    for e in endpoints:
        key = (e.method, e.path)
        if key not in seen:
            seen[key] = e
        else:
            # Prefer richer record (the one that carries parameters)
            if not seen[key].parameters and e.parameters:
                seen[key] = e
    return sorted(seen.values(), key=lambda e: (e.path, e.method))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Algorithm 1 — discover API endpoints (OAS + client code)")
    ap.add_argument("--oas", action="append", default=[],
                    help="OAS source (URL or file). Repeat for several specs.")
    ap.add_argument("--client-root", default=None,
                    help="Front-end root URL to crawl for JS-side routes.")
    ap.add_argument("--extra-routes", default=None,
                    help="Optional file: one METHOD PATH per line "
                         "(e.g. routes extracted via Diggy from an APK).")
    ap.add_argument("--out", required=True, help="Output JSON path.")
    args = ap.parse_args()

    if not (args.oas or args.client_root or args.extra_routes):
        ap.error("at least one of --oas / --client-root / --extra-routes")

    discovered: list[Endpoint] = []

    # 1. OAS documents -----------------------------------------------------
    for spec in args.oas:
        try:
            eps = parse_oas(spec)
            print(f"[oas] {spec}: {len(eps)} endpoints", file=sys.stderr)
            discovered.extend(eps)
        except Exception as exc:  # noqa: BLE001
            print(f"[oas] {spec}: FAILED ({exc})", file=sys.stderr)

    # 2. Client-side crawl --------------------------------------------------
    if args.client_root:
        eps = crawl_client(args.client_root)
        print(f"[client] {args.client_root}: {len(eps)} endpoints",
              file=sys.stderr)
        discovered.extend(eps)

    # 3. Extra hints --------------------------------------------------------
    if args.extra_routes:
        eps = parse_extra(args.extra_routes)
        print(f"[extra] {args.extra_routes}: {len(eps)} endpoints",
              file=sys.stderr)
        discovered.extend(eps)

    final = _dedupe(discovered)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump([e.as_dict() for e in final], fh, indent=2)
    print(f"[done] {len(final)} unique endpoints -> {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
