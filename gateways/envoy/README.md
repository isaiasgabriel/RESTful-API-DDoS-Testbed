<!-- Role: Usage notes for the Envoy gateway plug-in skeleton. -->
# Envoy gateway plug-in (skeleton)

This plug-in is an **experimental skeleton** to test HTTP/2 forwarding paths
without modifying Sock Shop application source code.

## What it does

- Exposes host `:8080` (HTTP/1.1) and `:8443` (TLS with ALPN `h2,http/1.1`).
- Serves `GET /healthz` with HTTP `200` on both listeners.
- Applies a local token-bucket rate limit of `100 requests/minute`.
- Adds `Retry-After: 60` on rate-limited responses.
- Routes all other traffic to `front-end:8079`.
- Tries to use **HTTP/2 upstream** via Envoy cluster protocol options.

## Important caveat

End-to-end HTTP/2 requires the upstream service to speak h2/h2c. If the
Sock Shop frontend only accepts HTTP/1.1, this skeleton will need adaptation
(for example, fallback to HTTP/1.1 upstream or a dedicated h2-capable
backend target) before it can be production-ready.

## Run

```bash
cd lab
API_GATEWAY=envoy ./start.sh
curl -s http://localhost:8080/healthz
curl -sk https://localhost:8443/healthz
```
