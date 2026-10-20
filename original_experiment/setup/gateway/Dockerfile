# Lab API gateway.
#
# The paper uses "a Spring Boot client serves as an API gateway" with three
# rate-limit policies (per X-API-KEY prefix, per IP, per USER).  In this lab
# we implement the *same* policies in OpenResty (Nginx + Lua) because it is
# (a) much faster to bring up than building a real Spring Cloud Gateway, and
# (b) exposes the exact same observable behaviour to the attacker (429 on
# rate-limit, full proxy to SockShop on the happy path).
#
# A reference Spring Cloud Gateway `application.yml` is provided alongside
# this Dockerfile for users who want to reproduce the test bed with the
# original Spring stack.
FROM openresty/openresty:1.25.3.1-0-alpine

# ratelimit.lua uses only ngx.shared.DICT primitives (built into OpenResty),
# so we don't need any extra Lua modules — just openssl for the lab cert.
RUN apk add --no-cache openssl curl

COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY ratelimit.lua /usr/local/openresty/nginx/conf/ratelimit.lua

# Lab self-signed cert so we can serve HTTP/2 over TLS.
RUN mkdir -p /etc/nginx/tls \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
       -keyout /etc/nginx/tls/key.pem \
       -out    /etc/nginx/tls/cert.pem \
       -subj "/CN=sockshop-gateway.local"

EXPOSE 8080 8443

CMD ["openresty","-g","daemon off;"]
