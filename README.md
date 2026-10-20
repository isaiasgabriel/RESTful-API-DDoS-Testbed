# Experimento atual — precisão de rate limiting

Este laboratório avalia as decisões de rate limiting de API gateways à frente do Sock Shop, começando pelo Kong com uma rota fixa (`GET /catalogue`) e identidade controlada. O piloto HTTP/1.1 valida a medição; os diagnósticos HTTP/2 investigam o comportamento sob concorrência.

**Comece pelo [roteiro de estudos](docs/study/STUDY_PLAN.md)** e pelo [mapa da aplicação](docs/study/APPLICATION_MAP.md). A [central de documentação](docs/README.md) reúne protocolo, estado registrado e relatórios.

## Organização

```text
lab/
├── gateways/              Sock Shop e configurações Kong, NGINX e Envoy
├── tests/                 Piloto HTTP/1.1, análise e testes de contrato
├── diagnostics/           Gerador, coleta e análise HTTP/2
├── results/               Evidências do experimento atual
├── docs/                  Estudos, metodologia, relatórios e histórico
├── start.sh               Inicialização dos gateways intercambiáveis
├── stop.sh                Encerramento da composição
├── requirements.txt       Dependências Python do experimento atual
└── original_experiment/  Reprodução do artigo, isolada da trilha atual
```

A descoberta de endpoints e a seleção automática de alvos pertencem ao [experimento original](original_experiment/README.md). Não são pré-requisitos do piloto atual.

## Sequência de leitura

1. [Configuração do Kong](gateways/kong/kong.yml) e [Compose base](gateways/base/docker-compose.yml).
2. [Protocolo experimental](docs/methodology/EXPERIMENTAL_PROTOCOL.md).
3. [Coletor HTTP/1.1](tests/pilot_kong_http1.py) e [analisador](tests/analyze_pilot_kong_http1.py).
4. [Gerador HTTP/2](diagnostics/http2_bounded.go), [orquestrador](diagnostics/run_bounded.py) e [analisador](diagnostics/analyze_bounded.py).

## Ambiente

Comandos a partir de `lab/`. A preparação Python é:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Para iniciar a composição Kong, após conferir que nenhuma outra composição ocupa as portas 8080/8443 ou os mesmos nomes de containers:

```bash
API_GATEWAY=kong ./start.sh
```

Sem `API_GATEWAY`, o lançador continua usando NGINX. Os detalhes de configuração estão nos READMEs de [Kong](gateways/kong/README.md), [NGINX](gateways/nginx/README.md) e [Envoy](gateways/envoy/README.md).

O [piloto](docs/reports/KONG_PILOT_2026-10-16.md) documenta sua execução e análise. Durante uma medição, sondagens adicionais podem consumir a cota. O script `stop.sh` e o teardown da suíte de contrato usam `down -v --remove-orphans`; considere esse efeito sobre volumes antes de executá-los.

## Limites das evidências

O último [estado experimental registrado](docs/status/CURRENT_STATUS.md) é de 16/10/2026. Os diagnósticos não substituem a campanha com repetições. Testes de contrato aprovados não comprovam equivalência matemática entre políticas nem precisão sob concorrência.

A separação de pastas não isola recursos em execução: o setup original ainda usa as mesmas portas e nomes de containers. Execute uma composição por vez. Resultados ficam fora do versionamento conforme `.gitignore` e precisam de backup próprio.

## Regressão local após alterações

O [validador dos gateways](diagnostics/README.md) verifica Kong, NGINX e Envoy com testes funcionais, carga HTTP/2 limitada e recuperação. A opção `--reuse-stack` da suíte preserva o ambiente em execução; `--report-dir` permite separar os relatórios de cada rodada.
