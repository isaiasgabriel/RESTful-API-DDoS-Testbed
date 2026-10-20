# Roteiro de estudos do projeto

Comece pela **sessão 1**, sem iniciar containers. A proposta é estudar em oito sessões de 60–90 minutos, adaptáveis ao seu ritmo. O primeiro objetivo é conseguir explicar uma requisição e sua medição de ponta a ponta.

Pré-requisitos que você pode revisar durante o percurso: métodos e status HTTP, JSON/YAML, funções Python, processos e portas, containers e redes Docker. Go e detalhes de HTTP/2 entram depois do piloto sequencial.

## Rotina de cada sessão

Reserve 10 minutos para lembrar o que aprendeu, 25–35 para leitura, 20–30 para o exercício e 5–10 para preencher o [diário](STUDY_JOURNAL.md). Registre uma explicação com suas próprias palavras e os arquivos que sustentam essa explicação.

## 1. Entender a pergunta do TCC

**Leia:** [mapa da aplicação](APPLICATION_MAP.md) e as seções “Situação em uma frase”, “Objetivo e escopo” e “Pendências prioritárias” do [estado consolidado](../status/CURRENT_STATUS.md).

**Exercício:** escreva cinco frases: qual é a aplicação, o papel do gateway, o que significa precisão, o que já foi observado e o que ainda falta demonstrar.

**Pode avançar quando:** conseguir distinguir a aplicação Sock Shop, a configuração dos gateways e os scripts de experimento. Saiba explicar por que um 429 pode ser uma decisão correta.

## 2. Seguir uma requisição

**Leia:** [Compose base](../../gateways/base/docker-compose.yml), [override Kong](../../gateways/kong/docker-compose.override.yml) e [kong.yml](../../gateways/kong/kong.yml), nessa ordem.

**Exercício:** desenhe o percurso de `GET /catalogue`. Anote portas do host e do container, upstream, serviço de catálogo e banco. Localize onde o arquivo de configuração é montado.

**Pode avançar quando:** explicar por que `/healthz` responder 200 não comprova que o catálogo está funcionando e onde o limitador pode interromper o percurso.

## 3. Entender a regra de limitação

**Leia:** [protocolo experimental](../methodology/EXPERIMENTAL_PROTOCOL.md), configuração Kong e [NGINX](../../gateways/nginx/nginx.conf).

**Exercício:** monte uma tabela de decisão para as requisições 1, 99, 100, 101 e 110 de uma origem, na mesma janela nova do piloto Kong. Depois explique por que mudar a identidade ou atravessar a fronteira de minuto altera o experimento.

**Pode avançar quando:** definir cota, identidade, janela, spillover e falso positivo, e explicar por que `100/min` sozinho não prova equivalência entre gateways.

## 4. Ler o piloto HTTP/1.1

**Leia:** [relatório do piloto](../reports/KONG_PILOT_2026-10-16.md), [coletor](../../tests/pilot_kong_http1.py) e [analisador](../../tests/analyze_pilot_kong_http1.py).

Siga a sequência: preparação → nova janela → identificação das requisições → respostas → logs → validação → métricas.

**Exercício:** escolha um `request_id` do CSV salvo e procure o mesmo identificador nos logs do gateway e do frontend. Compare uma resposta 200 e uma 429. Os artefatos estão em [results/pilot-kong-http1-20261016T201921Z-209215f3/](../../results/pilot-kong-http1-20261016T201921Z-209215f3).

**Pode avançar quando:** explicar como o recebimento no frontend confirma a admissão e por que o analisador só calcula métricas após validar a consistência da evidência.

## 5. Entender HTTP/2 e concorrência

**Leia:** [gerador diagnóstico Go](../../diagnostics/http2_bounded.go), [orquestrador Python](../../diagnostics/run_bounded.py) e [relatório HTTP/2](../reports/RESTART_LOAD_REPORT_2026-10-16.md).

**Exercício:** separe quatro quantidades: requisições totais, conexões, concorrência configurada e streams observados. Localize no código como são registrados protocolo e conexão. No relatório, identifique a evidência de streams sobrepostos.

**Pode avançar quando:** explicar por que solicitar concorrência 64 não basta para demonstrar 64 streams HTTP/2 simultâneos e por que os resultados 112/128 ainda não isolam o efeito do protocolo.

## 6. Ler resultados e limitações

**Leia:** [analisador HTTP/2](../../diagnostics/analyze_bounded.py), [auditoria operacional](../reports/OPERATIONAL_AUDIT_2026-10-16.md) e os arquivos `analysis.json` das rodadas citadas nos relatórios.

**Exercício:** faça uma tabela com condição, quantidade enviada, admissões, bloqueios, erros, janela, identidade e limitações. Separe observação de hipótese: “houve excesso nesta rodada” e “o timer causou o excesso” exigem evidências diferentes.

**Pode avançar quando:** explicar por que faltam repetições, controles de carga e uma referência para decisões concorrentes; diferencie timestamps de envio, chegada e conclusão.

## 7. Entender os testes de contrato

**Leia:** [testes de contrato](../../tests/test_rate_limiting.py), [fixtures](../../tests/conftest.py) e [comparação de relatórios](../../tests/comparison_report.py).

**Exercício:** liste o que cada teste verifica e o que ele não mede. Compare essas verificações com o piloto controlado. Observe no fixture as ações sobre containers e volumes antes de decidir executar testes.

**Pode avançar quando:** explicar por que cinco testes de contrato aprovados não substituem a avaliação de precisão sob concorrência.

A descoberta de endpoints e os algoritmos 1–5 estão no [experimento original](../../original_experiment/README.md). Essa leitura é opcional e não faz parte dos pré-requisitos do estudo atual.

## 8. Consolidar e planejar uma reprodução

**Leia:** novamente o protocolo e as pendências do estado consolidado. Consulte os guias de execução somente depois de escolher a trilha.

**Exercício:** prepare uma explicação de cinco minutos: problema → arquitetura → política → medição → evidência → limitações. Esboce uma ficha de execução com gateway/versão, configuração, identidade, endpoint, protocolo, volume, concorrência, janela, recursos, repetições e critérios de invalidação.

**Pode avançar quando:** outra pessoa conseguir entender, pela sua ficha, o que seria medido e quais condições tornariam uma rodada inválida.

## Primeira prática opcional: observar, antes de gerar carga

Todos os comandos abaixo partem da raiz `ddos/`. Eles inspecionam o ambiente ou enviam uma única requisição; não iniciam a composição.

```bash
cd lab
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

Se a composição Kong já estiver ativa e não houver uma medição em andamento:

```bash
curl --max-time 5 -i http://127.0.0.1:8080/catalogue
```

Confira status, corpo e cabeçalhos de limite. Se não houver ambiente ativo, continue estudando os dados salvos. Para uma reprodução posterior, use o procedimento do [piloto](../reports/KONG_PILOT_2026-10-16.md), após entender a inicialização em [start.sh](../../start.sh). O padrão desse lançador é NGINX; a escolha de Kong precisa ser explícita.

Sondagens também podem consumir a cota do IP: não misture essa prática com uma rodada de medição. O script `diagnostics/run_bounded.py` executa cargas; leia seus efeitos e parâmetros antes de rodá-los no laboratório local.

## O que deixar para depois

O walkthrough completo do artigo, os geradores de carga antigos e o Envoy podem esperar até você entender o piloto Kong. O código interno dos microserviços também pode ser estudado depois: inicialmente, a fronteira entre gateway, frontend e catálogo é suficiente para acompanhar a medição.
