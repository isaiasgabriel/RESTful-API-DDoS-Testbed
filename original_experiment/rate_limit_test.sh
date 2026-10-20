for i in $(seq 1 10); do
  curl -sS -o /dev/null -w "%{http_code} " \
       -H 'X-API-KEY: ZZ-same' -H 'X-Forwarded-For: 9.9.9.9' \
       -H 'X-User-Id: same' http://localhost:8080/catalogue
done; echo
