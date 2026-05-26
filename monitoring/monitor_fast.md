# terminal 1
cd lab && bash monitoring/monitor_fast.sh sockshop-gateway sockshop-orders sockshop-carts

# terminal 2 (start the attack any time after)
cd lab/attacks && go run algorithm5_http2_mux.go \
    -target https://localhost:8443 -targets-file ../results/targets.json \
    -clients 5 -requests 500 -streams 200 -insecure