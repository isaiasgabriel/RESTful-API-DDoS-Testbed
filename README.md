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
| `WALKTHROUGH.md`  | **Start here** for the paper lab. Runs all 5 algorithms against `setup/` (port 8080). |
| `MONITORING.md`   | How to capture CPU / latency / error rates and reproduce paper Tables II–IX and Fig. 3–4. |
| `setup/README.md` | Paper gateway (Section VI.B): rate-limit buckets, `docker compose` bring-up. |
| `gateways/*/README.md` | Per plug-in notes for Kong / NGINX (`start.sh`, port 80). |

## Project Layout

```
lab/
├── README.md                       This file
├── WALKTHROUGH.md                  Hands-on tutorial reproducing the paper
├── MONITORING.md                   CPU / latency / error-rate capture guide
├── start.sh                        Gateway plug-in launcher (Kong / NGINX)
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
│   └── algorithm5_http2_mux.go     Algorithm 5 – HTTP/2 multiplexed attack
├── gateways/                       Swappable API gateway plug-ins (see below)
│   ├── base/docker-compose.yml     Sock Shop core services (no gateway)
│   ├── nginx/                      NGINX plug-in + rate-limit config
│   └── kong/                       Kong OSS plug-in + declarative config
├── monitoring/
│   ├── monitor.sh                  CPU/mem/network sampling on the target
│   └── monitor_client.py           Latency + error-rate sampling from attacker
├── setup/                          Paper lab (Section VI.B) — use this for Algorithms 1–5
│   ├── docker-compose.yml          Sock Shop + paper gateway + Apache (ports 8080/8443)
│   ├── sockshop/                   Sock Shop manifests / overrides
│   └── gateway/                    Rate-limit gateway (OpenResty / Spring Cloud equiv.)
├── tests/
│   ├── conftest.py                 Pytest fixtures for gateway plug-in tests
│   ├── test_rate_limiting.py       Rate-limit contract tests (Kong / NGINX)
│   └── results/                    JSON reports per gateway (CI)
└── results/                        CSV / JSON output of attacks & monitors
```

## Two ways to start the lab

This repository exposes **two independent Docker stacks**. Pick the one that
matches what you are doing; they do not share the same compose files or ports.

| | **Paper lab** | **Gateway plug-in stack** |
|---|----------------|---------------------------|
| **Purpose** | Reproduce Section VI.B and run Algorithms 1–5 | Swap Kong / NGINX (or add gateways) without changing Sock Shop code |
| **Compose** | `setup/docker-compose.yml` | `gateways/base/` + `gateways/<name>/` via `start.sh` |
| **Entrypoint** | `cd setup && docker compose up -d` | `cd lab && ./start.sh` |
| **Gateway** | Custom rate-limiter in `setup/gateway/` (paper policies) | `nginx` or `kong` (select with `API_GATEWAY`) |
| **Host ports** | `8080` (HTTP/1.1), `8443` (TLS / HTTP/2) | `80` |
| **Health check** | `GET http://localhost:8080/health` | `GET http://localhost/healthz` |
| **Rate limits** | Per `X-API-KEY`, client IP, and `X-User-Id` (Table in `setup/README.md`) | Global 100 req/min per client IP |
| **Docs** | `WALKTHROUGH.md`, `setup/README.md` | `gateways/nginx/README.md`, `gateways/kong/README.md` |

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

### 2. Gateway plug-in stack (Kong / NGINX)

A separate compose layering path for **interchangeable** API gateways in front
of the same Sock Shop images. It does **not** implement the paper’s
`X-API-KEY` / `X-User-Id` buckets; it enforces a single global IP limit so
plug-ins can be compared and tested consistently.

```bash
cd lab
./start.sh                        # default: API_GATEWAY=nginx
API_GATEWAY=kong ./start.sh
curl -s http://localhost/healthz
```

For Kong, `REDIS_URL=redis://host:port` switches rate limiting to the Redis
strategy and starts the optional Redis service:

```bash
API_GATEWAY=kong REDIS_URL=redis://redis:6379 ./start.sh
```

Run the plug-in contract tests (from `lab/`, with dependencies installed):

```bash
pip install -r requirements.txt
pytest tests/test_rate_limiting.py --gateway nginx
pytest tests/test_rate_limiting.py --gateway kong
```

Tear down (example for nginx):  
`docker compose -f gateways/base/docker-compose.yml -f gateways/nginx/docker-compose.override.yml down -v`

#### Add a new gateway plug-in

1. Create `gateways/<name>/docker-compose.override.yml` with an `api-gateway`
   service that listens on host `:80`.
2. Implement the common contract:
   - proxy to `front-end:8079`
   - global 100 req/min per client IP
   - HTTP `429` + `Retry-After` on limit exceeded
   - `GET /healthz` returns HTTP `200`
   - forward `X-Forwarded-For` and `X-Real-IP`
3. Start it with `API_GATEWAY=<name> ./start.sh`.

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

## Quick start

The steps below use the **paper lab** (Section VI.B, `setup/` on port **8080**).
For the Kong/NGINX plug-in stack on port **80**, see
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

# 6. Algorithm 5 – HTTP/2 multiplexed attack (Go)
cd ../attacks

go run algorithm5_http2_mux.go \
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
| 5    | `algorithm5_http2_mux.go`                            | V.D.2         |

All scripts implement **X-API-KEY rotation** (cycling between keys that
match the gateway's three buckets — `AX001*`, `BX001*`, other — to bypass
the per-key rate limit, mirroring Section VI.B).

## Validating success

The paper considers an attack successful when the target shows **CPU ≥ ~90 %
for sustained periods** and/or **client-side latency rises above the normal
baseline** and/or **the gateway begins returning `429 / 503 / 509 / 520`**.
The two monitor scripts capture both the target-side and the attacker-side
view; correlate the CSVs to reproduce Tables II – IX and Fig. 3 – 4.
