> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

# Protocolo experimental — piloto

## Objetivo
Verificar se o Kong admite e bloqueia requisições conforme
a política de rate limiting configurada.

## Cenário inicial
- Gateway: Kong.
- Política: local, com limite configurado de 100 requisições/minuto por IP.
- Aplicação: Sock Shop.
- Cliente: uma única origem, sem rotação de identidade.
- Endpoint: `GET /catalogue`, validado com resposta 200 e catálogo JSON em 16/10/2026.
- Protocolo inicial: HTTP/1.1, para validar a medição.
- Etapa seguinte: repetir o cenário usando HTTP/2.

## Verificação inicial
Confirmar que o endpoint responde corretamente com poucas
requisições e registrar status e latência.

## Dados necessários
- Identificador da rodada e de cada requisição.
- Instante de envio e de chegada ao gateway.
- Identidade considerada pelo rate limiter.
- Status recebido pelo cliente.
- Evidência de encaminhamento ao backend.

## Questões que precisam ser resolvidas
- HTTP/2: o diagnóstico de 16/10 já registrou uma conexão e até 16/64 streams
  sobrepostos via frames; falta consolidar esse procedimento na campanha controlada.
- HTTP/2: como observar a ordem/instante de avaliação no limitador sem confundir timestamps de envio, chegada e conclusão?
- Como definir o oráculo e os denominadores para concorrência e para políticas diferentes da janela fixa?
- Como verificar novamente a identidade efetiva e ausência de tráfego concorrente em cada execução?

## Procedimento inicial validado — HTTP/1.1 sequencial

Em 16/10/2026 foi lido o código instalado no container `kong:3.7.1`:
o plugin básico `rate-limiting`, política `local`, utiliza janelas fixas
alinhadas ao minuto. A identidade é obtida por `kong.client.get_forwarded_ip()`.
O incremento local é agendado por timer; esse detalhe precisa ser considerado
na avaliação futura de concorrência e não comprova, sozinho, uma falha.

Para este piloto, aguardar um novo minuto do host mais dois segundos, sem sondas
durante a janela, e executar 110 GETs sequenciais com pausa de 100 ms após cada
resposta. Não enviar cabeçalhos de identidade ou encaminhamento. Não executar
outras cargas simultaneamente. Verificar os horários do gateway e exigir que
todas as requisições pertençam à mesma janela, com limite 100 e primeiro saldo 99.
Não reinicializar bancos nem apagar volumes.

Adicionar `pilot_id` único à query string permite correlacionar cliente,
access log do Kong e log do frontend. O parâmetro foi aceito pela rota e não
substitui a identidade por IP. O IP observado nesta execução foi `172.23.0.1`;
não presumir que será o mesmo em outro ambiente.

Referência deste caso sequencial: as primeiras 100 requisições devem ser
admitidas e as dez seguintes bloqueadas. Confirmar admissão pelo log do frontend
e pelo conteúdo de catálogo das respostas 200. Não classificar respostas 500 ou
falhas de transporte como admissões ou bloqueios corretos automaticamente.

Definições provisórias, restritas ao piloto: spillover = 100 × admissões após
a centésima requisição / 100; falsos positivos = 100 × rejeições 429 entre as
primeiras 100 / 100. O denominador do spillover é a cota, e o dos falsos positivos
é o número de admissões esperadas. Essas definições ainda precisam de alinhamento
com o orientador antes da campanha comparativa.

## Evidência inicial

Rodada `20261016T201921Z-209215f3`, executada entre 20:20:02 e 20:20:13 UTC:
100 respostas 200 com catálogo válido e 100 registros correspondentes no
frontend; dez respostas 429 sem registros correspondentes no frontend;
110 registros no gateway, todos no mesmo minuto e IP. Nenhum 500 ou erro de
transporte. Spillover e falsos positivos observados neste piloto: 0%.

Quatro coletas de recursos dos containers foram salvas em JSONL e CSV.
São dados diagnósticos de uma execução curta, sem demonstração de saturação.
O access log registra conclusão da requisição; não mede exatamente sua chegada.

Relatório e reprodução: [KONG_PILOT_2026-10-16.md](../reports/KONG_PILOT_2026-10-16.md).
Esta etapa valida a cadeia de medição sequencial; não valida HTTP/2 nem substitui
a campanha com repetições.

## Critério de conclusão do piloto
Conseguir explicar quais requisições foram admitidas,
quais foram bloqueadas e se as decisões respeitaram a política

## Atualização: diagnóstico HTTP/2 após reinício

Em 16/10, após reiniciar a composição preservando volumes, foram executadas
três etapas HTTP/2: 110 requisições sequenciais (100 admitidas), 1.600 em lotes
de 16 (112 admitidas) e 3.200 em lotes de 64 (128 admitidas). Cada etapa ocorreu
em um minuto e IP, com uma conexão e recebimentos confirmados no frontend.
O excesso agregado observado foi de 0%, 12% e 28% da cota de 100, respectivamente.
Não houve falhas de transporte ou respostas 500. A recuperação na janela
seguinte foi verificada com 200 e saldo 99.

Esses dados são diagnósticos, com uma execução por condição e carga oferecida
não equivalente entre etapas. Não há ainda taxa de falsos positivos por decisão
concorrente nem atribuição causal ao protocolo. Repetir uma condição congelada
e formalizar os controles antes de transformar esse diagnóstico em campanha.
Detalhes: [relatório de reinício e carga](../reports/RESTART_LOAD_REPORT_2026-10-16.md).
