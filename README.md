# RESTful API Application-Layer DDoS Vulnerability-Testing Lab

This repository is a faithful re-implementation of the methodology described
in:

> Sivakumar K., Santhi Thilagam P., *"Vulnerability Testing of RESTful APIs
> Against Application Layer DDoS Attacks"*, **IJACSA Vol. 16 No. 3, 2025**.

It implements Algorithms **1 – 5** of the paper end-to-end against the
[Weaveworks SockShop](https://github.com/microservices-demo/microservices-demo)
microservice-based demo application, fronted by a Spring Cloud Gateway that
enforces three rate-limit policies (per `X-API-KEY`, per `IP`, per `USER`),
exactly as described in Section VI.B of the paper.

## ⚠️ Legal / Ethical Notice

These scripts launch resource-exhaustion (Application-Layer DDoS) traffic.

**Use them ONLY on infrastructure you own or have explicit written
authorisation to test.** Running them against any third-party host is illegal
under most jurisdictions (CFAA, Computer Misuse Act, GDPR Art. 32, etc.) and
will be treated as a criminal denial-of-service attack.

The recommended environment is an air-gapped VM, a private docker host, or a
dedicated lab subnet with no route to the public internet.

## Topology (replicates Fig. 2 of the paper)

```
            ┌──────────────────────────────────────────────────────────┐
            │                  Attacker host (this repo)               │
            │   Algorithm 1 → 2 → 3/4 (HTTP/1.1) → 5 (HTTP/2)          │
            └──────────────────────────────────────────────────────────┘
                                    │
                                    ▼
   ┌──────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
   │ Apache httpd /   │ →  │ Spring Cloud Gateway │ →  │  SockShop micro-    │
   │ reverse proxy    │    │  (rate-limit by      │    │  services (Spring   │
   │ (HTTP/2 enabled) │    │   X-API-KEY/IP/USER) │    │  Boot / Tomcat)     │
   └──────────────────┘    └──────────────────────┘    └─────────────────────┘
```

## Documentation

| File              | When to read it                                           |
|-------------------|-----------------------------------------------------------|
| `README.md`       | This file — overview, layout, [two startup paths](#two-ways-to-start-the-lab). |
| `WALKTHROUGH.md`  | **Start here.** Paper lab (Algorithms 1–5, §1) + gateway plug-in pytest track (§2). |
| `MONITORING.md`   | How to capture CPU / latency / error rates and reproduce paper Tables II–IX and Fig. 3–4. |
| `setup/README.md` | Paper gateway (Section VI.B): rate-limit buckets, `docker compose` bring-up. |
| `gateways/*/README.md` | Per plug-in notes for Kong / NGINX / Envoy (`start.sh`, ports 8080/8443). |

## Project Layout

```
lab/
├── README.md                       This file
├── WALKTHROUGH.md                  Hands-on tutorial reproducing the paper
├── MONITORING.md                   CPU / latency / error-rate capture guide
├── start.sh                        Gateway plug-in launcher (Kong / NGINX / Envoy)
├── stop.sh                         Gateway plug-in shutdown wrapper (auto-detect supported)
├── requirements.txt                Python dependencies
├── algorithms/
│   ├── algorithm1_discover.py      Algorithm 1 – endpoint discovery
│   └── algorithm2_identify.py      Algorithm 2 – heavy-endpoint identification
├── attack_cli.py                   Interactive launcher for attacks/
├── attacks/
│   ├── algorithm3_symmetric.py     Algorithm 3 – HTTP/1.1 symmetric (httpx+mp)
│   ├── algorithm3_symmetric.sh     Algorithm 3 – CURL variant
│   ├── algorithm4_asymmetric.py    Algorithm 4 – HTTP/1.1 asymmetric (httpx+mp)
│   ├── algorithm4_asymmetric.sh    Algorithm 4 – CURL variant
│   ├── algorithm5_http2_mux.go     Algorithm 5 – original HTTP/2 multiplexed attack
│   └── algorithm5_http2_mux_fixed.go
│                                      Algorithm 5 – fixed standalone implementation
├── gateways/                       Swappable API gateway plug-ins (see below)
│   ├── base/docker-compose.yml     Sock Shop core services (no gateway)
│   ├── nginx/                      NGINX plug-in + rate-limit config
│   ├── kong/                       Kong OSS plug-in + declarative config
│   └── envoy/                      Envoy skeleton for HTTP/2 upstream experiments
├── monitoring/
│   ├── monitor.sh                  CPU/mem/network sampling on the target
│   └── monitor_client.py           Latency + error-rate sampling from attacker
├── setup/                          Paper lab (Section VI.B) — use this for Algorithms 1–5
│   ├── docker-compose.yml          Sock Shop + paper gateway + Apache (ports 8080/8443)
│   ├── sockshop/                   Sock Shop manifests / overrides
│   └── gateway/                    Rate-limit gateway (OpenResty / Spring Cloud equiv.)
├── tests/
│   ├── conftest.py                 Pytest fixtures (stack lifecycle + per-gateway reports)
│   ├── test_rate_limiting.py       Gateway-agnostic contract tests (single source of truth)
│   ├── verify_gateways.py          Run all plug-ins through the same verification pipeline
│   ├── comparison_report.py        Build tests/results/comparison_report.json
│   └── results/                    Per-gateway + comparison JSON (CI)
└── results/                        CSV / JSON output of attacks & monitors
```

## Two ways to start the lab

This repository exposes **two independent Docker stacks**. Pick the one that
matches what you are doing; they do not share the same compose files or ports.

| | **Paper lab** | **Gateway plug-in stack** |
|---|----------------|---------------------------|
| **Purpose** | Reproduce Section VI.B and run Algorithms 1–5 | Swap Kong / NGINX / Envoy (or add gateways) without changing Sock Shop code |
| **Compose** | `setup/docker-compose.yml` | `gateways/base/` + `gateways/<name>/` via `start.sh` |
| **Entrypoint** | `cd setup && docker compose up -d` | `cd lab && ./start.sh` |
| **Gateway** | Custom rate-limiter in `setup/gateway/` (paper policies) | `nginx`, `kong`, or `envoy` (select with `API_GATEWAY`) |
| **Host ports** | `8080` (HTTP/1.1), `8443` (TLS / HTTP/2) | `8080` (HTTP/1.1), `8443` (TLS / HTTP/2) |
| **Health check** | `GET http://localhost:8080/health` | `GET http://localhost:8080/healthz` |
| **Rate limits** | Per `X-API-KEY`, client IP, and `X-User-Id` (Table in `setup/README.md`) | Global 100 req/min per client IP |
| **Docs** | `WALKTHROUGH.md`, `setup/README.md` | `gateways/nginx/README.md`, `gateways/kong/README.md`, `gateways/envoy/README.md` |

### 1. Paper lab (Section VI.B) — default for this repository

This is the stack **described in the paper** (Fig. 2, Section VI.B): Apache
reverse proxy → API gateway with three rate-limit dimensions → Sock Shop
microservices. All attack scripts, monitoring, and the walkthrough assume
**this** environment on ports **8080** and **8443**.

```bash
cd lab/setup
docker compose pull
docker compose up -d --build
# wait ~60 s for microservices to be healthy
curl -s http://localhost:8080/health
curl -i -H 'X-API-KEY: AX001-demo' http://localhost:8080/catalogue
```

Tear down: `docker compose down -v` (from `lab/setup/`).

### 2. Gateway plug-in stack (Kong / NGINX / Envoy)

A separate compose layering path for **interchangeable** API gateways in front
of the same Sock Shop images. It does **not** implement the paper’s
`X-API-KEY` / `X-User-Id` buckets; it enforces a single global IP limit so
plug-ins can be compared and tested consistently.

```bash
cd lab
./start.sh                        # default: API_GATEWAY=nginx
API_GATEWAY=kong ./start.sh
API_GATEWAY=envoy ./start.sh      # experimental HTTP/2 upstream skeleton
curl -s http://localhost:8080/healthz
```

For Kong, `REDIS_URL=redis://host:port` switches rate limiting to the Redis
strategy and starts the optional Redis service:

```bash
API_GATEWAY=kong REDIS_URL=redis://redis:6379 ./start.sh
```

Envoy is currently provided as an **experimental skeleton** for HTTP/2
forwarding experiments; see `gateways/envoy/README.md` for caveats.

Stop stacks started by `start.sh`:

```bash
./stop.sh                # auto-detect running gateway
./stop.sh kong           # explicit gateway
./stop.sh all            # stop all gateway stack variants
```

#### Gateway equivalence verification

Every plug-in is validated with the **same** `tests/test_rate_limiting.py`
suite — no per-gateway test files and no gateway-conditional assertions.
A gateway is valid only if it passes all five cases with identical inputs
and thresholds.

**Verify one gateway** (start → healthz → pytest → report → tear down):

```bash
cd lab
pip install -r requirements.txt
pytest tests/test_rate_limiting.py --gateway nginx -v
# → tests/results/nginx_report.json
```

**Verify all contract gateways and compare** (recommended):

```bash
python3 tests/verify_gateways.py -v
# → tests/results/{gateway}_report.json for kong + nginx
# → tests/results/comparison_report.json  (verdict: equivalent | divergent)
```

Per-gateway steps (automated inside pytest `conftest.py`):

1. `API_GATEWAY=<name> ./start.sh`
2. `GET http://localhost:8080/healthz` → 200
3. `pytest tests/test_rate_limiting.py --gateway <name>`
4. All of: `test_under_limit`, `test_over_limit`, `test_retry_after`,
   `test_limit_resets`, `test_health_endpoint` must pass
5. Write `tests/results/<name>_report.json`
6. `docker compose … down -v`

If a plug-in fails, fix its **configuration** — do not weaken or skip tests.

#### Add a new gateway plug-in

1. Create `gateways/<name>/docker-compose.override.yml` with an `api-gateway`
   service that listens on host `:8080` (HTTP) and `:8443` (TLS).
2. Implement the common contract:
   - proxy to `front-end:8079`
   - global 100 req/min per client IP
   - HTTP `429` + `Retry-After` on limit exceeded
   - `GET /healthz` returns HTTP `200`
   - forward `X-Forwarded-For` and `X-Real-IP`
3. Start it with `API_GATEWAY=<name> ./start.sh`.
4. Run `python3 tests/verify_gateways.py --gateways <name> -v` — it must pass
   the full suite and appear as `"pass"` for every test in `comparison_report.json`.

## Attack launcher (interactive CLI)

After Algorithms 1–2 have produced `results/targets.json`, use the menu
launcher to pick and run any attack under `attacks/`:

```bash
cd lab
python3 attack_cli.py              # interactive menu
python3 attack_cli.py --list       # show keys: 3-py, 3-sh, 4-py, 4-sh, 5-go
python3 attack_cli.py -a 3-py      # run Algorithm 3 (Python) non-interactively
python3 attack_cli.py -a 5-go --clients 15 --requests 2000 --streams 200
```

Defaults match the Quick start below (`clients=15`, `requests=2000`,
`targets=results/targets.json`, Algorithm 5 → `https://localhost:8443`).
The menu launcher currently invokes the original `algorithm5_http2_mux.go`;
for the race-free fixed implementation, run
`attacks/algorithm5_http2_mux_fixed.go` directly as shown below.

## Quick start

The steps below use the **paper lab** (Section VI.B, `setup/` on port **8080**).
For the Kong/NGINX plug-in stack on ports **8080** / **8443**, see
[Two ways to start the lab](#two-ways-to-start-the-lab) above.

```bash
# 1. Paper lab: Sock Shop + Section VI.B gateway + Apache (Fig. 2)
cd setup
docker compose up -d
# wait ~60 s for all microservices to be healthy
curl -s http://localhost:8080/health | jq .

# 2. Algorithm 1 – discover all endpoints
python3 ../algorithms/algorithm1_discover.py \
    --oas http://localhost:8080/v3/api-docs \
    --client-root http://localhost:8080/ \
    --out ../results/endpoints.json

# 3. Algorithm 2 – pick the heavy ones
python3 ../algorithms/algorithm2_identify.py \
    --endpoints ../results/endpoints.json \
    --base-url  http://localhost:8080 \
    --api-key   AX001-benign \
    --out       ../results/targets.json

# 4a. Algorithm 3 – symmetric HTTP/1.1 attack (Python)
python3 ../attacks/algorithm3_symmetric.py \
    --target  ../results/targets.json \
    --clients 15 --requests 2000

# 4b. Algorithm 3 – CURL variant
bash ../attacks/algorithm3_symmetric.sh ../results/targets.json 2000 15

# 5. Algorithm 4 – asymmetric HTTP/1.1 attack
python3 ../attacks/algorithm4_asymmetric.py \
    --target ../results/targets.json --clients 15 --requests 2000

# 6. Algorithm 5 – HTTP/2 multiplexed attack (Go, fixed implementation)
cd ../attacks

go run algorithm5_http2_mux_fixed.go \
    -target https://localhost:8443 \
    -targets-file ../results/targets.json \
    -clients 15 \
    -requests 2000 \
    -streams 200 \
    -insecure

# 7. Monitor the target while attacking (open a 2nd terminal)
bash ../monitoring/monitor.sh   sockshop-gateway   ../results/monitor.csv
python3 ../monitoring/monitor_client.py \
    --target ../results/targets.json \
    --out ../results/client_latency.csv
```

## What each algorithm does

| Algo | File(s)                                              | Paper section |
|------|------------------------------------------------------|---------------|
| 1    | `algorithm1_discover.py`                             | V.A           |
| 2    | `algorithm2_identify.py`                             | V.B           |
| 3    | `algorithm3_symmetric.py` / `algorithm3_symmetric.sh`| V.D           |
| 4    | `algorithm4_asymmetric.py`/`algorithm4_asymmetric.sh`| V.D.1         |
| 5    | `algorithm5_http2_mux_fixed.go` recommended; `algorithm5_http2_mux.go` kept for comparison | V.D.2 |

All scripts implement **X-API-KEY rotation** (cycling between keys that
match the gateway's three buckets — `AX001*`, `BX001*`, other — to bypass
the per-key rate limit, mirroring Section VI.B).

### Algorithm 5 implementation note

Use `attacks/algorithm5_http2_mux_fixed.go` for new HTTP/2 multiplexing runs.
It is a standalone Go entrypoint with `//go:build ignore`, so it does not
conflict with the original `main` package during `go test ./...`, but it is
directly runnable with `go run algorithm5_http2_mux_fixed.go`.

The fixed version preserves the same CLI shape as the original and adds:

- per-request random generators, avoiding concurrent `math/rand.Rand` races;
- `StrictMaxConcurrentStreams: true`, so each worker stays on one HTTP/2
  connection instead of silently opening extras when peer stream limits apply;
- validation for invalid `-clients`, `-requests`, and `-streams` values;
- signal-aware cancellation;
- safer URL parsing and joining.

## Validating success

The paper considers an attack successful when the target shows **CPU ≥ ~90 %
for sustained periods** and/or **client-side latency rises above the normal
baseline** and/or **the gateway begins returning `429 / 503 / 509 / 520`**.
The two monitor scripts capture both the target-side and the attacker-side
view; correlate the CSVs to reproduce Tables II – IX and Fig. 3 – 4.
