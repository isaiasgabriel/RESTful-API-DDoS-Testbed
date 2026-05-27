<!-- Role: Usage notes for the Envoy gateway plug-in skeleton. -->
# Envoy gateway plug-in (skeleton)

This plug-in is an **experimental skeleton** to test HTTP/2 forwarding paths
without modifying Sock Shop application source code.

## What it does

- Exposes host `:8080` (HTTP/1.1) and `:8443` (TLS with ALPN `h2,http/1.1`).
- Serves `GET /healthz` with HTTP `200` on both listeners.
- Applies a local token-bucket rate limit of `100 requests/minute`.
- Adds `Retry-After: 60` on rate-limited responses.
- Routes traffic through an internal Envoy sidecar (`frontend-h2-sidecar`).
- Uses **HTTP/2** from edge Envoy -> sidecar, then HTTP/1.1 from sidecar -> `front-end:8079`.

## Important caveat

This achieves end-to-end h2 only up to the **h2-capable upstream target/service**
(the sidecar). Sock Shop frontend itself remains HTTP/1.1.

## Run

```bash
cd lab
API_GATEWAY=envoy ./start.sh
curl -s http://localhost:8080/healthz
curl -sk https://localhost:8443/healthz
```
