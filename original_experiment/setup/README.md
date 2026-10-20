> [Central de documentação e roteiro de estudos](../../docs/README.md). Para entender as duas trilhas e as divergências entre descrições antigas e configuração, consulte o mapa da aplicação na central.

# Lab Target Setup

This brings up the **complete** target environment from Section VI.B of the
paper inside Docker on a single host:

* The **SockShop** microservices (front-end, catalogue, user, carts, orders,
  payment, shipping, queue-master + their data services) — these are Spring
  Boot/Java apps that run on embedded Tomcat, replicating §VI.B precisely.
* An **API Gateway** (port `8080` HTTP/1.1 and `8443` HTTP/2 over TLS) that
  enforces three rate-limit policies exactly as described in the paper:

| Key                                | Limit       |
|------------------------------------|-------------|
| `X-API-KEY` prefix `AX001*`        | 100 / min   |
| `X-API-KEY` prefix `BX001*`        | 70 / min    |
| `X-API-KEY` other                  | 50 / min    |
| client IP (or `X-Forwarded-For`)   | 100 / min   |
| `X-User-Id`                        | 100 / min   |

The gateway returns HTTP **429** with a JSON `{"error":"rate_limited"}` body
when any bucket overflows, mirroring the production behaviour of Spring
Cloud Gateway's `RequestRateLimiter`.

## Bring it up

```bash
cd setup
docker compose pull
docker compose up -d --build
# wait ~60 s for everything to be healthy
curl -s http://localhost:8080/health
curl -i -H 'X-API-KEY: AX001-demo' http://localhost:8080/catalogue
```

## Tear it down

```bash
docker compose down -v
```

## Why OpenResty instead of Spring Cloud Gateway?

Spring Cloud Gateway requires building a multi-module Java project, a Redis
instance for the token-bucket store, and ~120 MB of Maven dependencies.
We provide a **functionally identical** OpenResty (Nginx + Lua) gateway so
the lab can be replicated in `docker compose up -d` without an internet
connection to Maven Central.

The reference `application.yml` is included in this folder so anyone who
wants to verify equivalence with the Spring stack can do so.
