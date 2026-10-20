# Local gateway regression validation

`validate_gateways.py` checks the current experiment against Kong, NGINX and Envoy, one at a time. It preserves volumes and leaves Kong selected at the end.

From `lab/`:

```bash
go build -o /tmp/tcc-gateway-validation-h2 diagnostics/http2_bounded.go
.venv/bin/python diagnostics/validate_gateways.py
```

The runner requires access to the Docker daemon, the gateway images and the Python dependencies in `requirements.txt`. It replaces the active gateway using `start.sh`; do not run it during another experiment.

For each gateway it performs:

1. HTTP/1.1 and HTTP/2 checks of `/healthz`, `/` and `/catalogue`, including catalogue content validation.
2. A 61-second cooldown followed by the five contract tests, using `--reuse-stack` and a separate `--report-dir`.
3. A bounded HTTP/2 load of 400 requests, concurrency 16, pauses of 100 ms between batches, request timeout 5 seconds and overall generator limit 40 seconds.
4. A 61-second cooldown and recovery checks, with container states, restarts and OOM status inspected.

Artifacts are written under a new `results/gateway-validation-<UTC timestamp>/` directory. Each gateway has startup logs, smoke results, a pytest report, request records, load summary, resource snapshots, recovery results and container logs. Historical reports under `tests/results/` are not overwritten.

This is a functional regression check, not a controlled comparison of rate-limiting precision. The load follows the contract tests without resetting counters. Policies and HTTP/HTTPS bucket sharing differ between gateways; do not interpret different admission counts as comparative accuracy. Resource snapshots do not measure peak usage or establish saturation. TLS certificate verification is disabled for these local test certificates.

`http2_bounded.go` is also used by the earlier Kong diagnostic `run_bounded.py`. The regression runner does not modify that diagnostic or its historical evidence. It verifies negotiation and observed client connections; it does not collect protocol frames to prove the number of simultaneously open streams.
