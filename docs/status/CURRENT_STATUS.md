> **Validação funcional em 20/10/2026:** Kong, NGINX e Envoy passaram em 15 testes de contrato e nas cargas HTTP/2 limitadas, com recuperação confirmada. [Relatório](../reports/GATEWAY_VALIDATION_2026-10-20.md). O estado experimental de precisão registrado abaixo continua sendo o de 16/10; a regressão não substitui a campanha pendente.

> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

# Estado atual do TCC e do laboratório

**Atualizado em 16 de outubro de 2026.** Este é o resumo principal para retomar o trabalho.
A fotografia detalhada anterior foi preservada em
[APPLICATION_STATUS_2026-10-06.md](../history/APPLICATION_STATUS_2026-10-06.md).
Esta atualização reúne a inspeção documental, o piloto HTTP/1.1, a auditoria
operacional das 17:49 e o reinício seguido de cargas HTTP/2, concluídas com
verificação de recuperação às **17:59 de 16/10/2026**, em São Paulo.
Detalhes: [auditoria](../reports/OPERATIONAL_AUDIT_2026-10-16.md) e
[reinício e carga](../reports/RESTART_LOAD_REPORT_2026-10-16.md).

## Reinício e cargas: resultado mais recente

Foram reiniciados os 14 serviços da composição Kong/Sock Shop, preservando
volumes. O sidecar antigo do Envoy continuou ativo fora dessa composição.
Depois foram executadas 4.910 requisições HTTP/2 em três etapas, cada uma em
uma janela de minuto, origem fixa e uma conexão TCP. Frames confirmaram máximos
de 1, 16 e 64 streams com respostas pendentes.

| Etapa | Requisições | HTTP 200 / recebimentos no frontend | HTTP 429 | Excesso sobre a cota de 100 |
|---|---:|---:|---:|---:|
| Sequencial HTTP/2 | 110 | 100 | 10 | 0 |
| Concorrência até 16 | 1.600 | 112 | 1.488 | 12 (12% da cota) |
| Concorrência até 64 | 3.200 | 128 | 3.072 | 28 (28% da cota) |

As admissões excedentes foram correlacionadas ao frontend e gateway, no mesmo
minuto e IP por etapa. Não houve 500, falhas de transporte ou resets de stream.
Na janela seguinte, `/catalogue` voltou a responder HTTP/2 200 com saldo 99;
Kong permaneceu saudável e os containers não tiveram reinício adicional observado.

Há agora **evidência diagnóstica de spillover sob concorrência HTTP/2** nesta
configuração. Foi uma execução por condição, variando também volume e pausa
entre lotes; isso ainda não estabelece repetibilidade nem causa exclusiva de
HTTP/2. Falsos positivos por requisição concorrente não foram calculados.
Foram salvas 16 amostras de recursos ao longo das três etapas; não foi demonstrada
saturação de CPU. Os detalhes, latências, recursos, limites e comandos estão no
[relatório das cargas](../reports/RESTART_LOAD_REPORT_2026-10-16.md).

## Auditoria operacional anterior às cargas

Foram confirmados 15 containers do projeto em execução, Kong 3.7.1 com healthcheck
saudável e configuração montada idêntica ao arquivo local. `/healthz` respondeu
200; `/catalogue` respondeu 200 com catálogo válido tanto por HTTP/1.1 quanto por
**HTTP/2 sobre TLS**, confirmado pelo cliente e pelo log do Kong. A consulta TLS
usou `--insecure`, sem validar confiança/nome do certificado. Uma única requisição
HTTP/2 não comprova multiplexação concorrente nem precisão sob concorrência.

O Docker informou **12 CPUs lógicas e aproximadamente 14,95 GiB de RAM** no host
Linux Mint 22.3. Nenhum dos 15 containers tinha limite explícito de memória,
quota de CPU ou afinidade nos campos inspecionados. Portanto, o ambiente atual
não comprova o cenário de VM dedicada com 8 vCPUs da proposta. Foram salvas
configurações, inventário, amostra de recursos, respostas e logs da auditoria.

## Situação em uma frase

Existe um piloto rastreável em HTTP/1.1 e um diagnóstico em HTTP/2 que confirmou
admissões acima da cota sob concorrência no Kong. A **avaliação experimental
sistemática ainda está pendente**, incluindo repetições, referência para falsos
positivos concorrentes e controles, assim como os capítulos finais.

## Objetivo e escopo

Título: “Precisão do Rate Limiting em API Gateways Self-Hosted sob Multiplexação
HTTP/2: Uma Avaliação Experimental”. Curso: Engenharia de Software, UTFPR Dois
Vizinhos; texto em português acadêmico com formatação SBC prevista.

A proposta original compara Kong, NGINX e Envoy por spillover e falsos positivos.
A recomendação discutida foi reduzir para Kong e NGINX, começando pelo Kong,
com alternativa de estudo de caso apenas no Kong se a medição consumir o prazo.
A retirada do Envoy e eventual mudança de título ainda dependem de alinhamento
com o orientador; não há aprovação registrada nesta conversa.

O usuário informou 26 dias até uma entrega obrigatória, com possibilidade de
correções posteriores. A disponibilidade de 4–8 horas foi interpretada no plano
como diária, mas essa unidade não foi confirmada explicitamente. A data absoluta
da entrega, a defesa e as regras das correções posteriores não foram informadas.
Os 26 dias são o prazo informado na conversa, não uma contagem atualizada automaticamente.

## Texto e materiais existentes

O PDF do TCC1 contém introdução, trabalhos relacionados, proposta, metodologia,
resultados esperados, resumo, abstract e referências. Há slides e roteiro para
conversa com o orientador. Não foram encontrados capítulos finais de resultados
experimentais, discussão e conclusão no material inspecionado.

O [protocolo experimental](../methodology/EXPERIMENTAL_PROTOCOL.md) foi atualizado com a rota,
o procedimento e a evidência do piloto. A referência de decisão para concorrência
HTTP/2 e os denominadores da comparação entre políticas ainda precisam ser fechados.
No PDF, 30 repetições e VM de 8 vCPUs/16 GB aparecem como exemplos metodológicos;
não comprovam uma campanha realizada nem isolamento experimental validado.

## Laboratório que já existia

Há Docker Compose com Sock Shop e configurações alternativas para Kong, NGINX e
Envoy, além de um laboratório separado com OpenResty/Lua. As alternativas
compartilham portas e nomes de containers; não devem ser iniciadas indiscriminadamente.

Existem geradores em Python, shell e Go. O gerador HTTP/2 corrigido ainda usa
cabeçalhos de identidade aleatórios e não registra conexões e streams efetivos.
Os lançadores principais continuam apontando para a versão original. Scripts de
monitoramento já existiam antes desta etapa.

Há relatórios históricos com cinco verificações básicas aprovadas para Kong e
NGINX em HTTP/1.1. O rótulo “equivalent” desses relatórios **não demonstra
 equivalência matemática das políticas nem precisão sob HTTP/2**. Envoy tem
configuração, mas não tem relatório equivalente e não está integrado à suíte atual.

Os CSVs HTTP/2 históricos registram bloqueios, erros 500 e uma execução com falha
ALPN. Não demonstram bypass, spillover, falsos positivos ou saturação. A origem dos
500 históricos continua sem diagnóstico conclusivo.

## O que foi executado em 16/10/2026

Após o usuário iniciar o Docker, foram inspecionados containers e configuração
Compose. Envoy estava ativo nas portas 8080/8443 e os bancos estavam parados.
O Compose base com override Kong substituiu o gateway e iniciou os serviços de
apoio, preservando os volumes. Não foi executado `down -v`.

Uma consulta a `GET /catalogue` pelo Kong retornou 200 com catálogo JSON.
Foi lido e preservado o código instalado do plugin básico `rate-limiting` do
Kong 3.7.1: política local, limite de 100/minuto/IP, janela fixa alinhada ao minuto,
identidade por `kong.client.get_forwarded_ip()` e incremento local agendado por
timer. O timer é um detalhe a investigar sob concorrência, não uma prova de falha.

Foram criados:

- [Coletor do piloto](../../tests/pilot_kong_http1.py): 110 GETs sequenciais, origem fixa,
  pausa de 100 ms após cada resposta, início no próximo minuto mais dois segundos.
- [Analisador](../../tests/analyze_pilot_kong_http1.py): correlação de IDs e status nos
  registros do cliente, Kong e frontend; exportação de recursos em CSV.
- [Relatório do piloto](../reports/KONG_PILOT_2026-10-16.md): procedimento, resultados,
  comandos de reprodução e limitações.

Cada requisição recebeu um `pilot_id` na query string. Foram salvos horários,
cabeçalhos, corpos, configuração, identificação da imagem, logs e recursos.
O coletor não zera contadores: usa uma nova janela e exige ausência de tráfego
concorrente. Os scripts passaram por compilação Python; houve execução real do
coletor e análise dos dados salvos.

## Resultado comprovado do piloto

Rodada `20261016T201921Z-209215f3`, entre 20:20:02 e 20:20:13 UTC
(17:20:02–17:20:13 em São Paulo), com IP observado `172.23.0.1`.

As primeiras **100 requisições retornaram 200**, com catálogo válido e registros
correspondentes no frontend. As **dez seguintes retornaram 429**, sem registros
correspondentes no frontend. Os 110 IDs aparecem uma vez no gateway, no mesmo
minuto e IP. O saldo diminuiu de 99 para zero. Não houve erro 500 nem falha de
transporte nessa rodada, nem outra requisição no log do gateway no intervalo conferido.

Para a referência sequencial de 100 admissões por janela, houve zero admissões
excedentes e zero rejeições indevidas: **spillover e falsos positivos de 0% neste
piloto**. Não generalizar esse resultado para concorrência ou outros gateways.

Foram salvas quatro amostras de recursos de gateway, frontend, catálogo e banco
em JSONL/CSV. Elas são diagnósticas; não demonstram saturação nem descrevem picos.
Os access logs registram conclusão, não o instante exato de chegada ao limitador.

Dados e validações:
[analysis.json](../../results/pilot-kong-http1-20261016T201921Z-209215f3/analysis.json),
[requests.csv](../../results/pilot-kong-http1-20261016T201921Z-209215f3/requests.csv) e
[resources.csv](../../results/pilot-kong-http1-20261016T201921Z-209215f3/resources.csv).

## Correções ao resumo antigo

O Git existe dentro de `lab`; a pasta superior não foi reconhecida como
repositório. Os dois scripts e o relatório novos ainda aparecem como arquivos não
rastreados, sem commit nesta etapa. Dados em `lab/results/` são ignorados pelo Git;
não foi criado nem verificado backup remoto.

O monitoramento não está mais apenas implementado: agora há amostras salvas do
piloto. Há também uma rota saudável comprovada e correlação de requisições com
recebimento no frontend. Isso não resolve os erros históricos de outras cargas.

Kong e o sidecar Envoy foram reconfirmados ativos após as cargas, às 17:59; o
sidecar permanece fora do caminho do Kong. Esse é o último estado operacional
observado, não uma garantia de execução no momento da leitura. Os novos arquivos
de diagnóstico e relatórios também precisam de versionamento; não foi feito commit.

## Pendências prioritárias e próximo passo

O próximo trabalho é repetir uma condição HTTP/2 concorrente congelada para
verificar estabilidade do excesso observado. Conexão, ALPN e streams sobrepostos
já foram registrados pelo novo gerador de diagnóstico, separado dos geradores
antigos. É preciso controlar a carga oferecida, reconstruir decisões esperadas
sob concorrência e tratar fronteiras de janela e incerteza temporal antes da campanha.

Antes da campanha, validar reinício de janela, estado inicial, critérios de
invalidação, duração e repetições. Alinhar com o orientador métricas e escopo.
Configurar e registrar recursos de forma estável. Se NGINX permanecer, avaliar
sua política própria: `100r/m` com `burst=100 nodelay` não equivale à janela fixa
do Kong. Envoy usa token bucket sem descritores por IP na configuração examinada.

Não foi identificada campanha final de 30 repetições por cenário. Depois da
validação HTTP/2, executar campanha, analisar resultados e escrever discussão e
conclusão. Atualizar metodologia, resumo/abstract, referências e formatação.
Demonstrar bypass ou esgotamento de CPU não é requisito para responder à pergunta
sobre precisão nas condições efetivamente avaliadas.

## Como retomar

Para repetir o piloto HTTP/1.1, seguir os comandos em
[lab/KONG_PILOT_2026-10-16.md](../reports/KONG_PILOT_2026-10-16.md).
Para entender a política e a referência de decisão, consultar
[EXPERIMENTAL_PROTOCOL.md](../methodology/EXPERIMENTAL_PROTOCOL.md).
Para o inventário técnico anterior, consultar a
[fotografia de 06/10](../history/APPLICATION_STATUS_2026-10-06.md), considerando as correções acima.
