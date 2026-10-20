# Experimento original — reprodução do artigo

Esta pasta preserva a trilha de reprodução dos algoritmos 1–5 do artigo que deu origem ao laboratório. Ela é uma referência histórica independente do fluxo de estudo do [experimento atual](../README.md).

O experimento atual utiliza uma rota conhecida e identidade controlada. Não precisa executar a descoberta, a seleção de alvos ou os geradores desta pasta.

```text
original_experiment/
├── algorithms/       Descoberta de endpoints e seleção de alvos
├── attacks/          Algoritmos 3–5 em Python, shell e Go; módulo Go próprio
├── setup/            Sock Shop com gateway OpenResty/Lua
├── monitoring/       Monitores usados pela trilha original
├── results/          Endpoints, alvos e CSVs históricos; novas saídas desta trilha
├── docs/             Guias históricos e README técnico anterior
├── requirements.txt  Dependências Python da trilha original
├── attack_cli.py     Menu dos geradores antigos
├── run_lab.sh        Orquestração dos algoritmos 1–5
└── rate_limit_test.sh Sondagem manual do limitador OpenResty
```

## Caminhos e dependências

Partindo da raiz `ddos/`, entre em `lab/original_experiment/`. Esse é o diretório de trabalho dos lançadores e dos exemplos relativos a `algorithms/`, `setup/`, `monitoring/` e `results/`.

```bash
cd lab/original_experiment
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python attack_cli.py --list
```

`--list` apenas lista os geradores. Os lançadores localizam scripts e resultados a partir da própria pasta. Para os exemplos de execução direta em Go, entre em `attacks/`, onde está o `go.mod`. As saídas históricas foram movidas sem alteração de conteúdo; os JSONs podem conter caminhos e URLs da execução original.

O setup OpenResty é autocontido: seu Compose continua em `setup/docker-compose.yml`, com build relativo a `setup/gateway/`. Ele compartilha portas e nomes de containers com o ambiente atual; a separação em disco não permite iniciar os dois simultaneamente.

## Consulta opcional

- [Setup OpenResty](setup/README.md).
- [Walkthrough do artigo](docs/WALKTHROUGH.md).
- [Monitoramento](docs/MONITORING.md) e [monitor rápido](docs/monitor_fast.md).
- [Explicação histórica do algoritmo 5](docs/algorithm5_http2_mux.md).
- [README técnico anterior](docs/LEGACY_TECHNICAL_README.md), que também contém referências à comparação de gateways agora mantida em `lab/`.

Os textos antigos preservam hipóteses e afirmações que não representam conclusões do experimento atual. Para as divergências conhecidas, consulte o [mapa da aplicação](../docs/study/APPLICATION_MAP.md). Os lançadores antigos continuam selecionando a versão original do algoritmo 5; esta reorganização não altera os algoritmos.
