> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

# Reinício e carga HTTP/2 do laboratório — 16/10/2026

## Resultado principal

Foram reiniciados os **14 serviços da composição Kong/Sock Shop**, preservando
containers e volumes. Depois foram executadas **4.910 requisições HTTP/2** em três
etapas, com uma conexão TCP por etapa e origem fixa. O gateway permaneceu saudável
e o catálogo respondeu normalmente na janela seguinte.

Houve admissões acima da cota de 100/minuto nas duas etapas concorrentes:
**112 admissões com até 16 streams pendentes e 128 com até 64**. Esses recebimentos
foram confirmados nos logs do frontend, no mesmo minuto e IP de cada etapa.
São evidências diagnósticas de spillover nesta configuração, ainda sem repetições
suficientes ou controles para uma conclusão comparativa ou causal sobre HTTP/2.

## Escopo e ambiente

Gateway: Kong 3.7.1, plugin básico `rate-limiting`, política local, limite
100/minuto/IP e janela fixa. Rota: `GET /catalogue`. A configuração do limitador
não foi alterada para executar as cargas. Os testes foram restritos a
`https://127.0.0.1:8443`, sem rotação de identidade ou cabeçalhos de encaminhamento.

O host do Docker tem 12 CPUs lógicas e aproximadamente 14,95 GiB de RAM, conforme
a auditoria anterior e a nova coleta do daemon. Gerador e alvo compartilham o host;
não foi estabelecido isolamento. Containers continuam sem os limites explícitos
de CPU e memória apontados na auditoria anterior. O sidecar antigo do Envoy
permaneceu ativo e foi monitorado, mas está fora da composição Kong reiniciada e
fora do caminho das requisições. Não foram testados NGINX ou Envoy como gateways.

O novo gerador usa Go 1.22.2 e apenas a biblioteca padrão. Ele mantém no máximo
uma conexão TCP para o host, exige resposta HTTP/2 e registra protocolo ALPN,
conexão e IDs por requisição. A verificação de confiança/nome do certificado TLS
foi desabilitada exclusivamente para o certificado do laboratório.

## Reinício e verificações de saúde

Foi executado `docker compose ... restart`, sem `down`, remoção de containers
ou exclusão de volumes. Os horários `StartedAt` dos 14 serviços da composição
mudaram para aproximadamente 20:53:05–20:53:16 UTC. O sidecar do Envoy manteve
seu horário anterior, 20:16:59 UTC.

Uma consulta HTTP/1.1 a `/catalogue` após o reinício retornou 200. Antes da carga,
o coletor exigiu Kong 3.7.1 com healthcheck `healthy` e todos os 15 containers do
projeto em execução. Ao final das cargas, os horários de início e contadores
de reinício permaneciam iguais aos registrados antes delas; nenhum container
estava parado ou marcado como `OOMKilled`. O campo `RestartCount=0` não significa
que o reinício manual não ocorreu: este foi confirmado pelos horários de início.

Às **20:59:02 UTC (17:59:02 em São Paulo)**, uma consulta de recuperação na nova
janela retornou HTTP/2 200, catálogo com nove itens e saldo de 99 requisições.
O Kong continuou `healthy`. Não foi validado o fluxo funcional completo de pedidos,
pagamentos, usuários ou entrega do Sock Shop.

## Procedimento das cargas

Cada etapa começou dois segundos depois de um novo minuto. Não foram enviadas
sondas durante a janela da carga. Cada lote termina antes de iniciar a pausa e
o lote seguinte. Portanto, os níveis abaixo são máximos de concorrência em rajadas,
não uma taxa contínua nem uma concorrência mantida durante toda a execução.

| Etapa | Início UTC | Requisições | Tamanho do lote | Pausa entre lotes | Duração ativa |
|---|---|---:|---:|---:|---:|
| c1 | 20:56:02 | 110 | 1 | 100 ms | 11,50 s |
| c16 | 20:57:02 | 1.600 | 16 | 150 ms | 15,46 s |
| c64 | 20:58:02 | 3.200 | 64 | 300 ms | 15,57 s |

Limites do gerador: até 5.000 requisições por etapa, até 64 simultâneas, timeout
de cinco segundos por requisição e prazo de 40 segundos para iniciar lotes.
Cinco falhas inesperadas interrompem os lotes seguintes; o lote em andamento
pode terminar. O orquestrador tem timeout adicional de 50 segundos por execução
e não avança de etapa se o gerador falhar ou um container estiver parado/OOM.
Nenhum desses critérios de interrupção foi acionado.

O diagnóstico salvou frames com `GODEBUG=http2debug=2`. A análise conta streams
desde HEADERS enviados até END_STREAM recebido. O maior número de respostas
pendentes foi 1, 16 e 64, respectivamente. Isso comprova streams sobrepostos na
conexão do cliente; não mede quantas requisições o servidor processava em CPU
simultaneamente. O servidor anunciou `MAX_CONCURRENT_STREAMS=128` no trace.
Todos os streams observados terminaram sem RST_STREAM. Não houve fallback HTTP/1.1.

## Resultados e rastreabilidade

| Etapa | HTTP 200 | HTTP 429 | HTTP 500 / erros de transporte | Recebimentos no frontend | Excesso sobre a cota | Excesso / cota |
|---|---:|---:|---:|---:|---:|---:|
| c1 | 100 | 10 | 0 | 100 | 0 | 0% |
| c16 | 112 | 1.488 | 0 | 112 | 12 | 12% |
| c64 | 128 | 3.072 | 0 | 128 | 28 | 28% |

O percentual acima é **100 × max(admissões − 100, 0) / 100**, com a cota no
denominador. Não é a fração das tentativas oferecidas que excedeu o limite.
Cada etapa teve uma única janela no log do gateway e o mesmo IP `172.23.0.1`.
Não apareceu tráfego concorrente estranho às etapas nos intervalos de access log
capturados desde o início de cada janela.

Foram conferidos IDs únicos, status cliente/gateway, HTTP/2 com ALPN `h2`, uma
conexão, catálogo válido para cada 200 e correspondência exata entre respostas
200 e IDs no frontend. As requisições 429 não aparecem no log do frontend.
Admissão não foi inferida apenas da ausência de status 429.

Na etapa sequencial, a ordem foi exatamente 100 admissões seguidas de dez
bloqueios, com zero falsos positivos nessa referência. Nas etapas concorrentes,
a **taxa de falsos positivos permanece não calculada**: ordem de envio, conclusão
e avaliação pelo limitador não são intercambiáveis. O excesso agregado confirmado
não exige atribuir uma ordem individual às decisões, mas essa ordem é necessária
para a classificação por requisição pretendida no trabalho.

## Latência e recursos

| Etapa | Média / p95 dos 200 | Média / p95 dos 429 | Amostras de recursos |
|---|---|---|---:|
| c1 | 5,53 / 7,98 ms | 1,26 / 1,64 ms | 4 |
| c16 | 27,51 / 39,88 ms | 2,39 / 3,70 ms | 6 |
| c64 | 105,49 / 158,10 ms | 6,92 / 11,20 ms | 6 |

Latências são medidas pelo cliente e incluem filas locais, transporte e servidor.
O p95 usa o elemento de índice `floor((n−1) × 0,95)` da série ordenada. Separar
200 e 429 evita interpretar a grande proporção de rejeições rápidas como melhora
de desempenho das admissões.

| Etapa | Maior CPU amostrada do Kong | Maior CPU amostrada do frontend | Maior ocupação média do host entre amostras |
|---|---:|---:|---:|
| c1 | 3,88% | 3,69% | 21,57% |
| c16 | 20,83% | 23,76% | 14,65% |
| c64 | 7,11% | 25,61% | 17,56% |

Percentuais de containers são os reportados por `docker stats`, sem divisão
pelo número de CPUs; 100% corresponde aproximadamente a um núcleo ocupado.
A coluna do host foi calculada por diferenças de `/proc/stat`, considerando
idle+iowait como ociosidade, e representa o host inteiro, incluindo outras tarefas.
Ela não é diretamente comparável ao percentual por container.

Também foram salvos memória, rede, I/O e PIDs dos 15 containers, `/proc/meminfo`
e load average. A coleta usa `docker stats --no-stream` e pausa de um segundo;
o tempo de coleta faz o intervalo efetivo ser maior. Os primeiros picos podem
ser perdidos. **Não foi demonstrada saturação de CPU**, e estas amostras não
excluem picos breves. O valor menor do Kong em c64 não prova menor consumo real.

## Interpretação e limites

O resultado novo é a observação rastreável de admissões acima da cota nas etapas
concorrentes. O incremento assíncrono visto no código do plugin é uma hipótese
plausível para investigar, mas a causa interna não foi instrumentada nem isolada.
Não há fundamento ainda para chamar isso de vulnerabilidade geral, afirmar
efeito exclusivo de HTTP/2 ou comparar produtos.

Foi realizada **uma execução por condição**. Variaram tamanho do lote, pausa,
volume total e carga oferecida. O sequencial não é um controle HTTP/1.1 com
concorrência e carga equivalentes. Logs de frames introduzem custo adicional,
gerador e alvo compartilham hardware, o sidecar e outros serviços permanecem
ativos e a confiança do certificado foi ignorada. Essas restrições impedem
uma conclusão causal ou estatística sobre o efeito isolado da multiplexação.

Os 500 e a falha ALPN históricos não foram reproduzidos, mas suas causas
continuam sem diagnóstico. As três etapas são testes de pressão acima da cota,
com limites explícitos; não constituem teste até a exaustão do servidor.

## Arquivos e comandos para reprodução

Dados desta execução:
[lab/results/restart-stress-20261016T205525Z/analysis.json](../../results/restart-stress-20261016T205525Z/analysis.json).
Cada subdiretório `c1`, `c16` e `c64` contém requisições JSONL/CSV, frames HTTP/2,
logs de gateway/frontend/catálogo, amostras de recursos JSONL/CSV, estado dos
containers e análise. A raiz contém configuração, metadados e hashes do gerador,
estado inicial/final e a consulta de recuperação. Os dados ocupam aproximadamente
17,4 MB antes de cópias adicionais dos scripts e continuam ignorados pelo Git.

Comandos usados, a partir de `/home/user/tcc/ddos`:

```sh
docker compose --project-directory /home/user/tcc/ddos/lab \
  -f lab/gateways/base/docker-compose.yml \
  -f lab/gateways/kong/docker-compose.override.yml restart

curl --http1.1 --noproxy '*' --max-time 10 -sS \
  -o /tmp/tcc-post-restart-catalogue.json \
  -w 'status=%{http_code} protocol=%{http_version}\n' \
  http://127.0.0.1:8080/catalogue

go build -o /tmp/tcc-http2-bounded lab/diagnostics/http2_bounded.go
python3 lab/diagnostics/run_bounded.py
python3 lab/diagnostics/analyze_bounded.py \
  lab/results/restart-stress-20261016T205525Z
```

Na repetição, usar no último comando o diretório novo informado pelo coletor.
O `restart` pressupõe que a composição Kong já esteja criada; não troca um
gateway Envoy por Kong. Se o ambiente estiver diferente, conferir a composição
antes. O gerador exige o caminho local fixo e não aceita alvos externos.
O orquestrador não reinicia serviços automaticamente. Não executar outras cargas
durante as etapas. A coleta leva alguns minutos devido à espera entre janelas.

Código:
[gerador Go](../../diagnostics/http2_bounded.go),
[orquestrador](../../diagnostics/run_bounded.py) e
[analisador](../../diagnostics/analyze_bounded.py).

## Próxima tarefa

Repetir uma condição concorrente congelada para verificar estabilidade e
variabilidade do excesso, preservando configuração, janela, identidade e logs.
Depois definir uma matriz com carga oferecida controlada, referência por decisão
e condições abaixo/acima da cota. Só então executar as repetições da campanha
final. A evidência atual deve ser discutida com o orientador como resultado
preliminar, não como conclusão final do TCC.
