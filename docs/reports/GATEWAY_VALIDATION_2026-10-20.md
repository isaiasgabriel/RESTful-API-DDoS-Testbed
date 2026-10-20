# Validação funcional dos gateways — 20/10/2026

A aplicação passou nas verificações executadas com Kong 3.7.1, NGINX 1.27.0 e Envoy 1.30.3 após a reorganização. Foram aprovados 15 testes de contrato e concluídas 1.200 requisições adicionais de carga HTTP/2, sem falhas inesperadas. A página inicial, o catálogo e a recuperação foram verificados em HTTP/1.1 e HTTP/2.

## Resultados da carga limitada

| Gateway | Testes de contrato | Requisições HTTP/2 | HTTP 200 | HTTP 429 | Falhas inesperadas | Recuperação |
|---|---:|---:|---:|---:|---:|---|
| kong | 5/5 | 400 | 96 | 304 | 0 | OK |
| nginx | 5/5 | 400 | 99 | 301 | 0 | OK |
| envoy | 5/5 | 400 | 100 | 300 | 0 | OK |

Cada carga usou concorrência configurada de 16, 400 requisições, pausa de 100 ms entre lotes, timeout de 5 segundos por requisição e limite de 40 segundos para o gerador. Foi observada uma conexão por gateway e pico de 16 requisições em andamento no cliente. Todas as respostas 200 da carga continham catálogo válido; não houve respostas 5xx ou erros de transporte. O gerador confirmou HTTP/2 em todas as 1.200 requisições.

## Procedimento

1. Inicializar uma composição de gateway por vez com os serviços Sock Shop.
2. Verificar `/healthz`, `/` e `/catalogue` por HTTP/1.1 e HTTP/2; validar o conteúdo do catálogo.
3. Esperar 61 segundos e executar os cinco testes de contrato: abaixo da cota, acima da cota, Retry-After, renovação do limite e endpoint de saúde.
4. Executar a carga HTTP/2 limitada e salvar requisições, sumário e amostras de recursos antes/depois.
5. Esperar 61 segundos e repetir as verificações funcionais; comparar estados e reinícios dos containers.

Em cada gateway, todos os containers inspecionados continuaram em execução, sem OOM marcado e sem incremento de reinícios durante a etapa. O Envoy foi validado com o sidecar previsto em sua configuração.

## Estado deixado ao final

Kong foi restaurado e passou novamente nas seis verificações HTTP/HTTP2. Os 14 serviços da composição Kong/Sock Shop estavam em execução, com Kong saudável. O sidecar exclusivo do Envoy foi parado depois da validação. Volumes foram preservados e outros projetos Docker não foram iniciados nem alterados.

Acesso local: `http://localhost:8080/` e `https://localhost:8443/`. O certificado TLS é de laboratório; os clientes de teste desativaram sua validação.

## Alterações necessárias na verificação

- A suíte agora aceita `--gateway envoy`.
- `--reuse-stack` permite testar uma composição já iniciada sem executar o teardown que remove volumes.
- `--report-dir` separa os relatórios desta execução dos históricos.
- Os testes abaixo da cota e após renovação agora exigem HTTP 200; antes aceitavam qualquer status diferente de 429, inclusive falhas de backend.
- Foi adicionado o [validador reproduzível](../../diagnostics/validate_gateways.py), documentado no [README dos diagnósticos](../../diagnostics/README.md).

Não foi necessário alterar configurações dos gateways para passar nesta rodada.

## Evidências

Rodada `gateway-validation-20261020T210509Z`:

- [Sumário por gateway](../../results/gateway-validation-20261020T210509Z/summary.json).
- [Kong](../../results/gateway-validation-20261020T210509Z/kong/), [NGINX](../../results/gateway-validation-20261020T210509Z/nginx/) e [Envoy](../../results/gateway-validation-20261020T210509Z/envoy/): logs, relatórios pytest, registros de requisições, recursos, estado e recuperação.
- [Verificação final do Kong](../../results/gateway-validation-20261020T210509Z/final-kong-smoke.json).

Os dados em `results/` são locais e ignorados pelo Git; este relatório não substitui seu backup.

## Limites da conclusão

Esta rodada confirma funcionamento dos caminhos testados, não de todos os fluxos de negócio da loja: cadastro, compra e pagamento completos não foram exercitados. As amostras de recursos não demonstram saturação nem medem picos.

As cargas ocorreram depois dos testes de contrato, sem zerar os contadores. Além disso, as políticas e o compartilhamento de cotas entre HTTP e HTTPS diferem entre gateways. Portanto, as contagens de 200/429 não devem ser usadas para comparar precisão, inferir spillover ou substituir a campanha com repetições. Não foram capturados frames nesta rodada para provar a quantidade de streams simultâneos.

O setup OpenResty do experimento original passou apenas na validação estática `docker compose config --quiet`; sua aplicação e seus geradores antigos não foram executados. O Docker Compose emitiu aviso de campo `version` obsoleto, sem falha de validação. A execução funcional acima cobre os três gateways do experimento atual.
