> **Separação do experimento original:** os caminhos `algorithms/`, `attacks/`, `setup/`, `monitoring/` e `results/` desta trilha agora partem de `lab/original_experiment/`. As seções sobre gateways e testes de contrato continuam partindo de `lab/`. Consulte o [README desta trilha](../README.md).

> [Índice de estudos](../../docs/README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

> Material de referência histórica. Para a arquitetura e as limitações conhecidas, comece pelo [mapa da aplicação](../../docs/study/APPLICATION_MAP.md). Afirmações antigas de equivalência, bypass ou saturação não substituem a medição experimental.

# terminal 1
cd lab/original_experiment && bash monitoring/monitor_fast.sh sockshop-gateway sockshop-orders sockshop-carts

# terminal 2 (start the attack any time after)
cd lab/original_experiment/attacks && go run algorithm5_http2_mux.go \
    -target https://localhost:8443 -targets-file ../results/targets.json \
    -clients 5 -requests 500 -streams 200 -insecure