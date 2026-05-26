<!-- Role: Usage notes for the NGINX gateway plug-in. -->
# NGINX gateway plug-in

This plug-in uses `nginx:1.27.0-alpine` to expose Sock Shop on host ports `8080` (HTTP) and `8443` (TLS).

## Contract compliance

- Listens on `:8080` (HTTP) and `:8443` (TLS) and proxies to `front-end:8079`.
- Enforces `100 requests/minute` per client IP using `limit_req_zone`.
- Uses `burst=100 nodelay` (aligned with the 100/min quota for contract equivalence).
- Returns HTTP `429` with:
  - header `Retry-After: 60`
  - body `{"error":"rate_limit_exceeded","retry_after":60}`
- Exposes `GET /healthz` with HTTP `200`.
- Passes `X-Forwarded-For` and `X-Real-IP` downstream.
