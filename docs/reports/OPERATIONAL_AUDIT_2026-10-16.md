> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

# Levantamento operacional do laboratório — 16/10/2026

**Atualização posterior:** este documento preserva a auditoria das 17:49.
Após ela foram reiniciados os serviços e executadas cargas HTTP/2 com excesso
de admissões observado. Consulte o
[relatório de reinício e carga](RESTART_LOAD_REPORT_2026-10-16.md)
e o [resumo principal atualizado](../status/CURRENT_STATUS.md).

**Verificação ao vivo:** 20:49:03–20:49:06 UTC, ou 17:49:03–17:49:06 em São Paulo.
Este levantamento complementa e atualiza a fotografia de 06/10, que não tinha
acesso ao Docker. Foram executadas inspeções do Docker, leitura de configuração
no container, coleta pontual de recursos e três GETs locais. Não foram alteradas
configurações, reiniciados containers, apagados volumes ou executadas cargas de estresse.

## Diagnóstico atual

O Kong está operacional, com uma rota do Sock Shop respondendo corretamente por
HTTP/1.1 e por HTTP/2 sobre TLS. Já existe um piloto sequencial HTTP/1.1 com
admissões e bloqueios correlacionados ao frontend. Ainda não existe uma avaliação
validada da precisão sob multiplexação HTTP/2 nem uma campanha comparativa final.

## Ambiente efetivamente observado

O daemon Docker informou Linux Mint 22.3, Docker 29.9.0, **12 CPUs lógicas** e
16.052.117.504 bytes de memória (aproximadamente 14,95 GiB). Isso descreve o host
atual do laboratório, não comprova uso de VM dedicada nem o cenário de 8 vCPUs
mencionado na proposta. Não foi verificado isolamento em relação a outros processos.

Os 15 containers do projeto `lab` estavam em execução. Todos tinham
`RestartCount=0` e `OOMKilled=false` na inspeção. Esses campos não constituem
histórico completo de falhas. Apenas o gateway apresentou estado de healthcheck
`healthy`; os demais não tinham resultado de healthcheck no campo consultado.
Container em execução não comprova saúde funcional de todas as rotas.

| Serviço/container | Imagem observada | Situação |
|---|---|---|
| gateway | `kong:3.7.1` | Em execução, healthy; versão confirmada por `kong version` |
| frontend | `weaveworksdemos/front-end:0.3.12` | Em execução; catálogo validado através dele |
| catalogue / catalogue-db | `weaveworksdemos/catalogue:0.3.5` / `weaveworksdemos/catalogue-db:0.3.0` | Em execução |
| user / user-db | `weaveworksdemos/user:0.4.7` / `weaveworksdemos/user-db:0.4.0` | Em execução; fluxo de usuários não testado |
| carts / carts-db | `weaveworksdemos/carts:0.4.8` / `mongo:3.4` | Em execução; fluxo de carrinho não testado |
| orders / orders-db | `weaveworksdemos/orders:0.4.7` / `mongo:3.4` | Em execução; fluxo de pedidos não testado |
| payment | `weaveworksdemos/payment:0.4.3` | Em execução; pagamento não testado |
| shipping / queue-master | `weaveworksdemos/shipping:0.4.8` / `weaveworksdemos/queue-master:0.3.1` | Em execução; entrega não testada |
| rabbitmq | `rabbitmq:3.6.8-management` | Em execução |
| frontend-h2-sidecar | `envoyproxy/envoy:v1.30.3` | Em execução, fora do caminho atual do Kong |

Em todos os 15 containers: `Memory=0`, `NanoCpus=0`, `CpuQuota=0` e `CpusetCpus`
vazio. Portanto, não há limites explícitos de memória, quota de CPU ou afinidade
de CPU nesses campos do Docker. Não confundir isso com ausência de qualquer
limitação do host ou limites de heap internos das aplicações.

O Kong publica 8080→8000 e 8443→8443. A rede observada é `lab_sockshop-net`.
NGINX não está ativo como gateway; o processo NGINX interno do Kong não é o
gateway NGINX independente previsto na comparação. O Envoy ativo é apenas o
sidecar remanescente, não uma validação da alternativa Envoy como gateway.

## Configuração do Kong conferida no container

`kong version` retornou `3.7.1`. O arquivo `/kong.yml` montado no container é
idêntico, byte a byte, ao arquivo local `lab/gateways/kong/kong.yml`, com SHA-256
`b28887f8a7d77291b71611d152b9553dfde346b3fcbefc42fbd15b5c364bfd98`.
As configurações NGINX geradas no container também foram preservadas.

A configuração mantém o plugin básico `rate-limiting`, `minute: 100`,
`policy: local`, `limit_by: ip`, `fault_tolerant: true` e cabeçalhos de limite
visíveis. O serviço aponta diretamente para `http://front-end:8079`.
A comparação dos arquivos montados não é uma consulta à API administrativa
do estado interno; a evidência de aplicação inclui também as respostas e o piloto.

A leitura do código instalado realizada no piloto mostrou janela fixa alinhada
ao minuto e incremento local agendado por timer. Não há evidência de política
Redis ou janela deslizante ativa nesta configuração.

## Sondas executadas agora

Cada GET recebeu um `audit_id` para correlação nos logs. Foram apenas três
requisições, sem simultaneidade. Elas podem consumir a cota corrente; não devem
ser misturadas a uma rodada experimental na mesma janela.

| Consulta | Resultado do cliente | Evidência adicional |
|---|---|---|
| HTTP/1.1 `http://127.0.0.1:8080/healthz` | 200 | Registro no gateway; sonda local, não saúde global do backend |
| HTTP/1.1 `http://127.0.0.1:8080/catalogue` | 200, catálogo JSON válido | Mesmo `audit_id` no gateway e frontend |
| HTTP/2 `https://127.0.0.1:8443/catalogue` | 200, `http_version=2`, catálogo JSON válido | Gateway registra `HTTP/2.0`; mesmo `audit_id` no frontend |

A consulta HTTPS usou `--insecure` para o certificado do laboratório: a confiança
e o nome do certificado **não foram validados**. A negociação resultou efetivamente
em HTTP/2; não foi apenas uma tentativa com fallback para HTTP/1.1. Isso confirma
conectividade HTTP/2 cliente→Kong nesta configuração, não multiplexação de streams
concorrentes, precisão do limitador sob concorrência ou HTTP/2 até o Sock Shop.
A falha ALPN histórica não foi reproduzida nessa sonda, mas sua causa antiga
não foi identificada por este teste.

## Monitoramento

Uma amostra de `docker stats` dos 15 containers foi salva. No instante observado,
Kong apresentou 1,20% de CPU e 787,3 MiB de memória. São valores pontuais,
anteriores às três sondas, sem caracterização de picos ou saturação.

Além desta inspeção, o piloto anterior do mesmo dia tem quatro amostras de gateway,
frontend, catálogo e banco, em JSONL e CSV. A afirmação de 06/10 de que não havia
dados de monitoramento está superada. Ainda falta uma coleta adequada à campanha
HTTP/2, incluindo avaliação de interferência do gerador e do host.

## Evidências anteriores revisadas, sem repetir as cargas

O piloto `20261016T201921Z-209215f3` registrou 110 GETs HTTP/1.1 sequenciais:
100 respostas 200, recebidas pelo frontend, e dez 429, sem registros correspondentes
no frontend. Os IDs e status foram correlacionados ao gateway. Não houve 500 ou
falha de transporte. Spillover e falsos positivos foram 0% nessa rodada, segundo
a referência sequencial. Não é uma campanha final nem resultado sobre multiplexação.

As contagens dos quatro CSVs históricos HTTP/2 foram recalculadas nesta revisão:

| Arquivo | Registros | 429 | 500 | Falhas de transporte |
|---|---:|---:|---:|---:|
| `h2mux_1779892979.csv` | 2.500 | 0 | 0 | 2.500 |
| `h2mux_1779893143.csv` | 2.500 | 2.203 | 297 | 0 |
| `h2mux_1779893225.csv` | 2.500 | 2.095 | 405 | 0 |
| `h2mux_fixed_1779906971.csv` | 30.000 | 29.900 | 100 | 0 |

Essas cargas continuam sem referência e rastreabilidade suficientes para afirmar
bypass, precisão ou saturação. A ausência de 500 nas sondas atuais não explica os
802 erros 500 históricos.

Os relatórios antigos de Kong e NGINX continuam registrando cinco verificações
básicas aprovadas em HTTP/1.1. Não foram reexecutadas: a suíte inclui encerramento
com `down -v --remove-orphans`, inadequado para uma inspeção que preserve o ambiente.
O rótulo `equivalent` desses relatórios não prova equivalência entre políticas.

## Código, Git e texto acadêmico

O repositório está em `lab`, no commit `551b1e5`, de 27/05/2026. O relatório do
piloto e os dois novos scripts ainda estão não rastreados. Dados em `results/`
são ignorados pelo Git. Não foi verificado backup remoto. A pasta superior não
foi reconhecida como repositório na inspeção anterior; não confundir isso com
ausência de Git no laboratório.

Foi reconfirmado no código que os lançadores usam o gerador HTTP/2 original,
enquanto o corrigido continua com identidades aleatórias, timestamps em segundos
e sem registro de conexões/streams efetivos. A suíte aceita Kong/NGINX, não Envoy.
As políticas NGINX, Kong e Envoy continuam diferentes; não foram alteradas agora.

O estado do texto é o da inspeção documental anterior: proposta, metodologia,
trabalhos relacionados, resultados esperados, resumo/abstract e referências
existem; resultados finais, discussão e conclusão não foram encontrados. Nesta
auditoria operacional não foi feita nova revisão integral do PDF.

## O que falta para responder à pergunta de pesquisa

O próximo marco é um piloto **HTTP/2 concorrente e rastreável**: manter rota e
identidade, observar conexão e streams efetivos, definir decisão esperada e
tratar ordem de avaliação e fronteiras de janela. O sucesso da sonda HTTP/2
reduz a incerteza de conectividade, mas não resolve essas questões.

Depois, estabilizar recursos e cenário, alinhar métricas e escopo com o orientador,
validar repetições independentes e executar a campanha. Ainda não foi identificada
campanha final de 30 repetições por cenário. NGINX depende de sua própria referência
de decisão; Envoy permanece candidato a corte de escopo, sem aprovação registrada.

## Evidências e reprodução

Arquivos da auditoria em
[lab/results/audit-runtime-20261016T204903Z/summary.json](../../results/audit-runtime-20261016T204903Z/summary.json).
O diretório contém inventário sanitizado dos containers, limites de recursos,
informações do daemon, configuração montada, cabeçalhos e corpos das sondas,
protocolos observados e logs correlacionados. Não foram copiados valores de
variáveis de ambiente dos containers nem chaves TLS privadas.

O coletor executado foi preservado em
[collect_runtime.py](../../results/audit-runtime-20261016T204903Z/collect_runtime.py).
Para repetir esta inspeção no mesmo workspace, com Docker ativo e sem campanha
experimental concorrente:

```sh
cd /home/user/tcc/ddos
python3 lab/results/audit-runtime-20261016T204903Z/collect_runtime.py
```

Ele cria outro diretório datado e executa novamente as três sondas. Os caminhos
do workspace e os nomes dos containers estão fixados no coletor. Não inicia
serviços automaticamente. O coletor e os dados estão dentro de `results/`,
ignorado pelo Git, e precisam de preservação separada.

O [resumo principal](../status/CURRENT_STATUS.md) consolida o trabalho.
O [relatório do piloto](KONG_PILOT_2026-10-16.md) documenta as 110 requisições.
A [fotografia de 06/10](../history/APPLICATION_STATUS_2026-10-06.md) permanece preservada
como registro histórico, com as limitações e informações superadas explicitadas aqui.
