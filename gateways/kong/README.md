> [Central de documentação e roteiro de estudos](../../docs/README.md). Para entender as duas trilhas e as divergências entre descrições antigas e configuração, consulte o mapa da aplicação na central.

<!-- Role: Usage notes for the Kong gateway plug-in. -->
# Kong gateway plug-in

This plug-in uses `kong:3.7.1` in DB-less declarative mode and exposes the
Sock Shop entrypoint on host ports `8080` (HTTP/1.1) and `8443` (TLS).

## Contract compliance

- Listens on `:8080` (HTTP) and `:8443` (TLS) and proxies all routes to `front-end:8079`.
- Enforces `100 requests/minute` per client IP globally.
- Returns `429` when the limit is exceeded (with Kong standard rate-limit headers).
- Exposes `GET /healthz` with HTTP `200`.
- Passes `X-Forwarded-For` (Kong default) and injects `X-Real-IP`.

## Rate-limit strategy

- Default strategy: `local`.
- If `REDIS_URL` is provided to `start.sh`, the launcher sets Kong to `redis`
  policy and enables the optional `redis` service profile.
