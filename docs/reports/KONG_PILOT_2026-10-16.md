> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

# Piloto Kong — 16 de outubro de 2026

## Resultado

O caminho Kong → frontend Sock Shop → catálogo respondeu corretamente a
`GET /catalogue`. Uma rodada sequencial HTTP/1.1 produziu exatamente 100 respostas
200 seguidas de dez 429, sem erros 500 nem falhas de transporte. As primeiras
100 requisições têm registros individuais no frontend; as dez bloqueadas não
aparecem nesse log. Os 110 identificadores estão presentes uma vez no gateway.

Rodada: `20261016T201921Z-209215f3`.
Execução: 20:20:02–20:20:13 UTC (17:20:02–17:20:13 em São Paulo).
IP observado pelo gateway: `172.23.0.1`.
Versão: Kong 3.7.1, plugin básico, limite 100/minuto/IP, política local.
O primeiro saldo foi 99, o centésimo foi zero; as rejeições mantiveram saldo zero.
Nenhuma outra requisição apareceu no log do gateway desde o início da janela
até o final da coleta. Os JSONs do catálogo foram validados como listas não
vazias com campos `id` e `name`.

Neste caso sequencial, a referência admite as primeiras 100 requisições e
rejeita as restantes. O excesso de admissões dividido pela cota foi 0/100;
as rejeições indevidas divididas pelas admissões esperadas foram 0/100.
Portanto, os dois percentuais são 0% **nesta única rodada diagnóstica**.

## Ambiente e ações realizadas

Depois de iniciar o Docker, o Envoy estava ativo e os bancos estavam parados.
Foi executado o Compose base com o override Kong: o gateway foi substituído e
os serviços de apoio iniciados, preservando volumes. Não foi executado `down -v`.
O sidecar antigo do Envoy permanece ativo, fora do caminho do Kong; outros
serviços do Sock Shop também estão ativos. Não há isolamento de recursos validado.

Uma consulta inicial ao catálogo retornou 200 antes da rodada. Nenhum erro 500
foi reproduzido nesse endpoint; isso não explica os 500 das execuções históricas.
A versão instalada do código do limitador foi salva: usa janela fixa de minuto,
identidade por `get_forwarded_ip()` e incremento local agendado por timer.

## Arquivos

Dados em `results/pilot-kong-http1-20261016T201921Z-209215f3/`:

- `metadata.json`, `kong.yml`: identificação da execução, imagem e hash da configuração.
- `handler.lua`, `policies.lua`, `timestamp.lua`: código instalado consultado.
- `requests.csv` e `response-001.json` até `response-110.json`: dados do cliente, cabeçalhos e corpos.
- `sockshop-gateway.log`, `sockshop-frontend.log`, `sockshop-catalogue.log`: evidências do alvo.
- `resources.jsonl`, `resources.csv`: quatro amostras de gateway, frontend, catálogo e banco do catálogo.
- `summary.json`: contagens do coletor; `analysis.json`: validações cruzadas e métricas do piloto.

`results/` já é ignorado pelo Git. Os dados estão no disco local e precisam de
backup separado; este trabalho não criou nem verificou um backup remoto.
O metadado original dizia que não havia log independente de recebimento no
backend; a inspeção posterior encontrou os IDs no frontend. Essa limitação foi
resolvida para o frontend nesta rodada, como demonstrado em `analysis.json`.
O catálogo registra operações bem-sucedidas, mas não os IDs do piloto.

## Reprodução

Na pasta `lab`, com Docker ativo e sem outras cargas:

```sh
docker compose --project-directory . -f gateways/base/docker-compose.yml -f gateways/kong/docker-compose.override.yml up -d
python3 tests/pilot_kong_http1.py
python3 tests/analyze_pilot_kong_http1.py results/pilot-kong-http1-20261016T201921Z-209215f3
```

No último comando, substituir o diretório pelo informado na nova execução.
O coletor espera o próximo minuto mais dois segundos e para ao encontrar erro
de transporte, status inesperado ou catálogo inválido. Código de saída zero do
coletor não implica validade experimental: executar e inspecionar o analisador.
O script passou por compilação Python e execução real; o analisador conferiu
os 110 registros contra os logs do gateway e do frontend.

## Limites e próximo passo

Este resultado não avalia multiplexação, bypass, saturação ou equivalência de
gateways. Uma conexão HTTP/1.1 foi reutilizada pelo cliente, sem concorrência.
Timestamps do cliente não são tempos de chegada ao gateway; access logs são
registros de conclusão. A ordem é interpretável aqui porque o envio é sequencial.
As quatro amostras de recursos não caracterizam picos nem esgotamento de CPU.

Próxima tarefa: adaptar a medição para HTTP/2 mantendo a rota e identidade,
confirmar negociação TLS/ALPN e registrar conexões e concorrência efetivas.
Antes da campanha, validar também reinício de janela, instrumentação temporal,
referência de decisão concorrente e configuração estável de recursos.
