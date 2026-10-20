> **Separação do experimento original:** os caminhos `algorithms/`, `attacks/`, `setup/`, `monitoring/` e `results/` desta trilha agora partem de `lab/original_experiment/`. As seções sobre gateways e testes de contrato continuam partindo de `lab/`. Consulte o [README desta trilha](../README.md).

> [Índice de estudos](../../docs/README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

> Material de referência histórica. Para a arquitetura e as limitações conhecidas, comece pelo [mapa da aplicação](../../docs/study/APPLICATION_MAP.md). Afirmações antigas de equivalência, bypass ou saturação não substituem a medição experimental.

# Monitoring & Validation Guide

To prove that the algorithms actually exhaust the target — i.e. to reproduce
Tables II – IX and Figures 3 – 4 of the paper — you need to record **three
quantities simultaneously** during each attack run:

| # | Quantity                          | Where it is captured             |
|---|-----------------------------------|----------------------------------|
| 1 | Target-side CPU / memory          | `monitoring/monitor.sh`          |
| 2 | Client-side latency               | each attack CSV (`latency_ms`)   |
| 3 | Server-reported overload codes    | each attack CSV (status column)  |

Below are the canonical setups for each (matching §VI.D of the paper).

## 1. Target-side CPU & memory

### Quick path (Docker container)

```bash
# In a second terminal, BEFORE you start the attack:
bash monitoring/monitor.sh sockshop-gateway results/monitor.csv 1
```

This emits one CSV row per second:

```
timestamp,cpu_percent,mem_used_mb,mem_limit_mb,net_rx_bytes,net_tx_bytes,blk_read_bytes,blk_write_bytes,pids
1715549123,8.42,87.2,2048.00,123456,9876,...
1715549124,93.10,512.1,2048.00,123567,9931,...
```

When you import that CSV into any plotting tool (Excel, gnuplot, matplotlib,
Grafana) you'll see the CPU climb to the ~90 – 100 % range during HTTP/2 +
multi-client multiplexing — the exact effect the paper reproduces in Table
VII (HTTP/2 + 15 clients ≈ 95 % CPU).

### Bare-metal / PID-based monitoring

If the target is *not* containerised, point the monitor at a PID:

```bash
# e.g. SockShop running natively, JVM pid = 12345
MONITOR_PID=12345 bash monitoring/monitor.sh _ results/monitor.csv 1
```

### Production-grade alternative

For higher fidelity, run a Prometheus + Node Exporter + cAdvisor sidecar in
the `setup/docker-compose.yml` and scrape:

* `node_cpu_seconds_total{mode!="idle"}` — host CPU
* `container_cpu_usage_seconds_total{name="sockshop-gateway"}` — container CPU
* `http_server_requests_seconds_count` — Spring Boot Actuator metric

The paper used **New Relic / AppDynamics** for this purpose; Prometheus is a
drop-in open-source equivalent.

## 2. Client-side latency / error rates

Every attack script writes a CSV with a `status` and `latency_ms` column per
request. You don't need extra tooling — but if you want a *live* dashboard
while the attack is running, fire up `monitor_client.py` in a third terminal:

```bash
python3 monitoring/monitor_client.py \
    --target results/targets.json \
    --out    results/client_latency.csv \
    --interval 1.0 \
    --duration 300
```

This pings the heaviest endpoints once per second with a *fixed* API key
(it intentionally doesn't rotate, so it must not contribute to bypass-traffic),
and prints a live status line:

```
21:36:14 POST   /orders                                  →  503    8412.3 ms   [2xx=12 4xx=0 5xx=4 ovr=6 err=2]
```

A spike in `5xx`, `ovr` (429/503/509/520), or `err` proves the gateway /
backend is failing under the attack — exactly the "expected outcome"
described at the end of §V.D.

## 3. Aggregating the results

Once both monitors are written, you can correlate them with this one-liner:

```bash
python3 - <<'PY'
import csv, statistics
with open("results/monitor.csv") as fh:
    cpu = [float(r["cpu_percent"]) for r in csv.DictReader(fh) if r["cpu_percent"]]
with open("results/symmetric_py_1715549100.csv") as fh:
    lat = [float(r["latency_ms"]) for r in csv.DictReader(fh)
           if r["status"].isdigit() and int(r["status"]) > 0]
print(f"target CPU  max={max(cpu):.1f}%  p95={sorted(cpu)[int(len(cpu)*0.95)]:.1f}%")
print(f"client lat  p50={statistics.median(lat):.0f} ms  p95={sorted(lat)[int(len(lat)*0.95)]:.0f} ms")
PY
```

If `max CPU ≥ 90 %` and `p95 latency` is significantly above the no-attack
baseline (which you should record once first, with zero attack traffic), the
attack is successful per the paper's criteria.

## 4. Reproducing each paper table

| Table     | Algorithm                | Clients | Requests | Protocol |
|-----------|--------------------------|---------|----------|----------|
| II        | algorithm3_symmetric.py  | 1       | 500–2000 | HTTP/1.1 |
| III       | algorithm3_symmetric.sh  | 1       | 500–2000 | HTTP/1.1 |
| IV        | algorithm3_symmetric.sh  | 5       | 500–2000 | HTTP/1.1 |
| V         | algorithm3_symmetric.sh  | 15      | 500–2000 | HTTP/1.1 |
| VI        | algorithm5_http2_mux.go  | 1       | 500–2000 | HTTP/2   |
| VII       | algorithm5_http2_mux.go  | 5 / 15  | 500–2000 | HTTP/2   |
| VIII      | algorithm4_asymmetric.sh | 1       | 500–2000 | HTTP/1.1 |
| IX        | algorithm4_asymmetric +  | 15      | 500–2000 | both     |
|           | algorithm5_http2_mux.go  |         |          |          |

For each row, run with `--requests N --clients C`, record the CSV, and
compare the `max(cpu_percent)` of `monitor.csv` against the table value.

## 5. Stopping a runaway attack

* `Ctrl-C` on any attack script terminates that worker tree (the Python
  scripts use `multiprocessing.Pool` which propagates SIGINT to children).
* The Go binary respects `Ctrl-C` via `context.Cancel()`.
* If a process is wedged, `pkill -f algorithm` cleans up everything started
  by this repo.
* `docker compose down -v` from `setup/` tears the whole target stack down.
