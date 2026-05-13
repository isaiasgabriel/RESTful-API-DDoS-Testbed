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
| `README.md`       | This file — overview, layout, quick commands.             |
| `WALKTHROUGH.md`  | **Start here.** Step-by-step tutorial that runs all 5 algorithms against the live lab, with expected outputs and validation. |
| `MONITORING.md`   | How to capture CPU / latency / error rates and reproduce paper Tables II–IX and Fig. 3–4. |
| `setup/README.md` | Notes about the API-gateway implementation choice (OpenResty vs Spring Cloud Gateway). |

## Project Layout

```
lab/
├── README.md                       This file
├── WALKTHROUGH.md                  Hands-on tutorial reproducing the paper
├── MONITORING.md                   CPU / latency / error-rate capture guide
├── requirements.txt                Python dependencies
├── algorithms/
│   ├── algorithm1_discover.py      Algorithm 1 – endpoint discovery
│   └── algorithm2_identify.py      Algorithm 2 – heavy-endpoint identification
├── attacks/
│   ├── algorithm3_symmetric.py     Algorithm 3 – HTTP/1.1 symmetric (httpx+mp)
│   ├── algorithm3_symmetric.sh     Algorithm 3 – CURL variant
│   ├── algorithm4_asymmetric.py    Algorithm 4 – HTTP/1.1 asymmetric (httpx+mp)
│   ├── algorithm4_asymmetric.sh    Algorithm 4 – CURL variant
│   └── algorithm5_http2_mux.go     Algorithm 5 – HTTP/2 multiplexed attack
├── monitoring/
│   ├── monitor.sh                  CPU/mem/network sampling on the target
│   └── monitor_client.py           Latency + error-rate sampling from attacker
├── setup/
│   ├── docker-compose.yml          Brings up SockShop + Gateway + Apache
│   ├── sockshop/                   SockShop manifests / overrides
│   └── gateway/                    Spring Cloud Gateway with rate-limit conf
└── results/                        CSV / JSON output of attacks & monitors
```

## Quick start

```bash
# 1. Stand up the target lab (SockShop + API gateway + Apache reverse proxy)
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
    -streams 200 -clients 15 -requests 2000

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
