> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

> Material de referência histórica. Para a arquitetura e as limitações conhecidas, comece pelo [mapa da aplicação](../study/APPLICATION_MAP.md). Afirmações antigas de equivalência, bypass ou saturação não substituem a medição experimental.

# Project Summary for AI Evaluation

## Purpose

This project is a lab implementation for evaluating RESTful API vulnerability to application-layer DDoS techniques, based on the paper:

Sivakumar K., Santhi Thilagam P., "Vulnerability Testing of RESTful APIs Against Application Layer DDoS Attacks", IJACSA Vol. 16 No. 3, 2025.

The implementation targets the Weaveworks Sock Shop microservice demo behind API gateway rate limiting. It includes endpoint discovery, target identification, HTTP/1.1 attack drivers, HTTP/2 multiplexing attack drivers, monitoring utilities, and gateway equivalence tests.

## Main Work Completed

1. Paper-oriented lab stack
   - Added `lab/setup/docker-compose.yml` for Sock Shop plus a custom gateway on host ports `8080` and `8443`.
   - Added OpenResty/Lua gateway implementation in `lab/setup/gateway/ratelimit.lua`.
   - Implemented the paper's three rate-limit dimensions:
     - `X-API-KEY` prefix `AX001*`: 100 requests/minute.
     - `X-API-KEY` prefix `BX001*`: 70 requests/minute.
     - Other API keys: 50 requests/minute.
     - Client IP or `X-Forwarded-For`: 100 requests/minute.
     - `X-User-Id`: 100 requests/minute.
   - Gateway returns HTTP `429`, `Retry-After: 60`, and a JSON rate-limit body when a bucket overflows.

2. Algorithm implementations
   - `lab/algorithms/algorithm1_discover.py` implements endpoint discovery from OpenAPI specs, client-side HTML/JS scraping, and optional manual route hints.
   - `lab/algorithms/algorithm2_identify.py` probes discovered endpoints, records latency/status, classifies high-latency and error-prone endpoints, and writes `targets.json`.
   - `lab/attacks/algorithm3_symmetric.py` implements HTTP/1.1 symmetric attack traffic using multiprocessing and rotating `X-API-KEY`, `X-Forwarded-For`, and `X-User-Id`.
   - `lab/attacks/algorithm4_asymmetric.py` implements HTTP/1.1 asymmetric attack traffic using multiple endpoints, mutated paths/query values, and rotating identifiers.
   - `lab/attacks/algorithm5_http2_mux.go` contains the original HTTP/2 multiplexing implementation.
   - `lab/attacks/algorithm5_http2_mux_fixed.go` contains a corrected standalone HTTP/2 implementation with per-worker clients, safer random number usage, flag validation, cancellation handling, and CSV output.
   - Shell variants exist for Algorithms 3 and 4.

3. Gateway plug-in stack
   - Added a separate gateway comparison path under `lab/gateways/`.
   - `lab/start.sh` starts Sock Shop with a selectable API gateway using `API_GATEWAY=nginx`, `API_GATEWAY=kong`, or `API_GATEWAY=envoy`.
   - `lab/stop.sh` handles shutdown.
   - NGINX and Kong plug-ins are implemented with a common global 100 requests/minute per-client-IP contract.
   - Kong supports optional Redis-backed rate limiting through `REDIS_URL=redis://host:port`.
   - Envoy is present as an experimental HTTP/2 upstream skeleton.

4. Gateway equivalence testing
   - `lab/tests/test_rate_limiting.py` is the gateway-agnostic contract suite.
   - Tests verify:
     - under-limit traffic does not receive `429`;
     - over-limit traffic receives at least one `429`;
     - `429` includes `Retry-After`;
     - rate-limit window resets after about 60 seconds;
     - `/healthz` returns HTTP `200`.
   - `lab/tests/verify_gateways.py` runs the same pytest suite for Kong and NGINX and writes comparison reports.
   - `lab/tests/comparison_report.py` builds a pass/fail equivalence report.

5. Monitoring and documentation
   - `lab/monitoring/monitor.sh` records target-side Docker CPU, memory, network, block I/O, and PID count.
   - `lab/monitoring/monitor_client.py` records live client-side latency/error behavior against selected targets.
   - [MONITORING.md](../../original_experiment/docs/MONITORING.md) describes how to reproduce paper tables and correlate CPU with latency/error results.
   - [WALKTHROUGH.md](../../original_experiment/docs/WALKTHROUGH.md) gives a step-by-step reproduction flow for Algorithms 1-5 and gateway plug-in tests.
   - `lab/README.md` documents the two independent stack modes: the paper lab and the gateway plug-in comparison stack.

## Generated Evidence Present in Workspace

Generated result files are already present under `lab/results/` and `lab/tests/results/`.

Endpoint and target discovery:
   - `lab/results/endpoints.json` contains 14 discovered endpoints.
   - `lab/results/targets.json` was generated at `2026-05-12T21:52:04` for `http://localhost:8080`.
   - Algorithm 2 selected 10 target endpoints:
     - `DELETE /cart`
     - `GET /cart`
     - `GET /catalogue/{id}`
     - `GET /customers/{id}`
     - `GET /orders`
     - `POST /addresses`
     - `POST /cards`
     - `POST /cart`
     - `POST /orders`
     - `POST /register`
   - Top latency-selected endpoint was `GET /orders`.

Gateway equivalence reports:
   - `lab/tests/results/kong_report.json`: all five tests passed.
   - `lab/tests/results/nginx_report.json`: all five tests passed.
   - `lab/tests/results/comparison_report.json`: verdict is `equivalent`, with no divergences.

HTTP/2 attack CSVs:
   - `lab/results/h2mux_1779892979.csv`: 2,500 rows, all status `-1`; errors indicate TLS ALPN/protocol negotiation failure.
   - `lab/results/h2mux_1779893143.csv`: 2,500 rows; 2,203 HTTP `429`, 297 HTTP `500`; average latency about 79.6 ms.
   - `lab/results/h2mux_1779893225.csv`: 2,500 rows; 2,095 HTTP `429`, 405 HTTP `500`; average latency about 224.1 ms.
   - `lab/results/h2mux_fixed_1779906971.csv`: 30,000 rows; 29,900 HTTP `429`, 100 HTTP `500`; average latency about 44.3 ms.

## Important Caveats for Evaluation

The repository is not currently recognized as a Git repository from `/home/user/tcc/ddos`, so there is no local commit history available for evaluation.

The saved HTTP/2 attack outputs mostly show rate-limit saturation or server errors, not a clean demonstrated bypass. The first saved HTTP/2 run failed due to TLS protocol negotiation. Later runs reached the gateway/server and produced mostly `429` responses, with some `500` responses. An evaluator should not treat the existing CSVs as conclusive proof that the rate-limiter bypass succeeded.

The documentation describes the expected bypass behavior through rotating `X-API-KEY`, `X-Forwarded-For`, and `X-User-Id`, and the attack scripts implement that rotation. However, the generated evidence currently present should be interpreted as load/rate-limit behavior evidence unless new runs with matching monitor CSVs demonstrate CPU exhaustion and sustained bypass.

No target-side monitoring CSV was found in `lab/results/` during this inspection. To reproduce the paper-style validation, run `lab/monitoring/monitor.sh` during attack execution and correlate it with attack CSV latency/status data.

## How to Evaluate Quickly

1. Read `lab/README.md` and [WALKTHROUGH.md](../../original_experiment/docs/WALKTHROUGH.md) to understand the two stack modes.
2. Inspect `lab/setup/gateway/ratelimit.lua` to verify the paper-style rate-limit policy.
3. Inspect Algorithms 1-5 under `lab/algorithms/` and `lab/attacks/`.
4. Review generated outputs under `lab/results/`.
5. Review `lab/tests/results/comparison_report.json` for gateway equivalence evidence.
6. Optionally rerun gateway tests:

```bash
cd lab
python3 tests/verify_gateways.py -v
```

7. For paper-style attack validation, rerun the paper stack, start target monitoring, run Algorithms 1-5, and compare CPU, latency, HTTP status, and transport error behavior.
