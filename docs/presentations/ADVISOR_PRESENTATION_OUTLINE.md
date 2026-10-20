> [Índice de estudos](../README.md). Documento reorganizado em 20/10/2026; datas e resultados abaixo preservam o registro original. Caminhos em comandos continuam relativos ao diretório indicado no texto, não a esta pasta.

# Roteiro de apresentação ao orientador

**Tema:** funcionamento do laboratório e próximos passos do TCC sobre precisão de rate limiting em Kong, NGINX e Envoy sob multiplexação HTTP/2.

**Duração estimada:** 12 a 15 minutos, incluindo transições e pausas. Os trechos entre aspas são sugestões de fala.

**Base:** código do laboratório, avaliação dos arquivos de resultados e projeto `TCC1_Final_Isaias-Gabriel-Miranda-Sampaio.pdf`, especialmente as seções 3, 4 e 5. Este roteiro descreve o estado inspecionado; as modificações abaixo são propostas, não implementações concluídas.

## 1. Apresentação do problema e da aplicação — 1 minuto

“O objetivo do meu TCC é avaliar com que precisão Kong, NGINX e Envoy aplicam limites de requisições quando recebem cargas HTTP/2 multiplexadas. Quero medir tanto requisições admitidas acima do permitido, chamadas de spillover, quanto requisições bloqueadas indevidamente, ou falsos positivos.

Para isso, tenho um laboratório que combina uma aplicação de referência, gateways e ferramentas de geração de carga e monitoramento. A aplicação usada como alvo é o Sock Shop, uma demonstração de comércio eletrônico formada por microsserviços de catálogo, usuários, carrinho, pedidos, pagamento e entrega.

O laboratório também contém geradores inspirados no artigo de Sivakumar e Thilagam. Essa parte apoia a construção do experimento. A pergunta principal do TCC, porém, é a precisão dos gateways: encontrar ausência de bypass também é um resultado válido.”

**Transição:** “Vou explicar primeiro o caminho de uma requisição e depois como o laboratório gera e registra a carga.”

## 2. Arquitetura e duas formas de execução — 1 minuto

“O fluxo básico é: o gerador envia uma requisição ao gateway, o gateway aplica a política de rate limiting e, se permitir, encaminha a requisição ao Sock Shop. Os serviços e bancos executam em containers Docker, conectados pela rede interna `sockshop-net`. O cliente acessa o gateway pela porta 8080 para HTTP ou 8443 para HTTPS com HTTP/2.

Existem duas stacks. A primeira é a adaptação do laboratório do artigo, iniciada pelo Compose de `lab/setup`. Ela usa um gateway próprio em OpenResty e Lua, que encaminha várias rotas diretamente aos microsserviços.

A segunda usa `lab/start.sh`, com a variável `API_GATEWAY`, para escolher Kong, NGINX ou Envoy. Kong e NGINX encaminham as rotas de aplicação ao frontend do Sock Shop. No Envoy, há também um sidecar que recebe HTTP/2 do gateway e encaminha HTTP/1.1 ao frontend.

Essas variantes são executadas alternadamente porque reutilizam portas e nomes de containers. Os geradores e monitores são scripts executados separadamente, fora dos serviços da aplicação.”

**Apoio visual opcional:** `Gerador → gateway selecionado → Sock Shop`, com coleta de métricas no cliente, gateway e backend. Na variante Envoy, mostrar o sidecar entre gateway e frontend.

## 3. Como o rate limiting funciona — 1 minuto

“No gateway próprio, o script Lua mantém contadores em memória compartilhada por janelas fixas de 60 segundos. Cada contador combina uma identidade com o minuto atual. Quando o minuto muda, passa a ser usado outro contador.

A requisição é verificada em três dimensões, nesta ordem: API key, IP e usuário. O prefixo da API key define uma cota de 100, 70 ou 50 requisições por minuto, mas o contador é individual por chave completa. IP e usuário têm cota de 100. A primeira dimensão excedida produz uma resposta 429 e interrompe o encaminhamento.

Nos gateways plugáveis, a implementação atual é diferente. Kong usa o plugin de rate limiting com limite por IP e política local. NGINX usa leaky bucket, com taxa média de 100 por minuto e capacidade de rajada. Envoy usa token bucket local, com capacidade de 100 tokens e reposição periódica.

Portanto, configurar o mesmo número nominal não torna os algoritmos idênticos. O experimento precisa considerar a regra de janela, rajada e reposição de cada um para distinguir comportamento esperado de erro de precisão.”

## 4. Descoberta de endpoints e geração de carga — 1 minuto e 30 segundos

“A preparação começa no Algoritmo 1. Ele reúne endpoints de documentos OpenAPI, de caminhos encontrados no HTML e JavaScript do frontend e de um arquivo opcional de dicas manuais. O resultado é uma lista em JSON.

O Algoritmo 2 faz sondagens nesses endpoints, registra latências e status e seleciona candidatos por maior latência ou presença de erros. Essa seleção é uma heurística; não mede diretamente o custo computacional de cada endpoint.

Os Algoritmos 3 e 4 geram carga HTTP/1.1 nas versões Python. No simétrico, o alvo e o payload são repetidos. No assimétrico, variam os endpoints, parâmetros de caminho, query e corpos. Cada cliente é um processo que envia requisições sequencialmente; os processos executam em paralelo.

O Algoritmo 5 usa Go e HTTP/2. Cada worker tem seu próprio cliente HTTP, e goroutines enviam requisições concorrentes. O parâmetro streams limita as operações em andamento por worker. Por exemplo, 15 workers com 2.000 requisições cada programam 30.000 requisições; com limite de 200 operações por worker, o teto no gerador é de 3.000 operações concorrentes.

Isso não comprova automaticamente 3.000 streams ativos na rede. O transporte e o servidor também impõem limites. A versão corrigida espera capacidade de streams em vez de abrir conexões adicionais apenas para contornar esse limite, além de corrigir aleatoriedade compartilhada e cancelamento. O orquestrador atual ainda chama a versão original.

Outro ponto importante é que os geradores alternam cabeçalhos de identidade. Para estudar o efeito específico da multiplexação, essa variação precisa ser separada do experimento principal.”

## 5. Coleta de dados e testes disponíveis — 1 minuto

“Os geradores registram uma linha por tentativa em CSV, com worker, número da tentativa, timestamp, status e latência. As versões assimétricas e HTTP/2 também incluem método e caminho. Os arquivos ainda não registram as identidades enviadas nem os identificadores de conexão e stream.

O monitor de alvo consulta estatísticas Docker de CPU, memória, rede e disco de um container. O monitor de cliente faz requisições sequenciais com uma chave fixa, registrando status e latência. Ambos usam pausa padrão de um segundo entre coletas ou chamadas; o período efetivo também inclui o tempo da operação.

Há uma suíte que inicia a stack, executa cinco testes e gera um relatório por gateway. Ela verifica ausência de 429 abaixo de uma carga pequena, presença de 429 após mais requisições, cabeçalho Retry-After, recuperação após espera e endpoint de saúde.

O relatório comparativo chama os gateways de equivalentes quando todos esses testes passam. Esse termo representa apenas a regra do relatório: os testes atuais são sequenciais em HTTP/1.1 e não medem equivalência de precisão sob HTTP/2.”

## 6. Estado atual: o que foi observado — 1 minuto

“Kong e NGINX têm cinco testes aprovados cada, totalizando dez aprovações. Isso confirma o funcionamento das verificações básicas implementadas. Envoy ainda não tem relatório nessa suíte.

Nos três arquivos de carga que receberam respostas HTTP, foram registradas 35.000 respostas: 34.198 foram 429, ou 97,71%, e 802 foram 500, ou 2,29%. Na maior execução, houve 29.900 respostas 429 e 100 respostas 500.

Existe ainda uma execução com 2.500 falhas de negociação TLS/ALPN. Ela deve ser tratada como falha de infraestrutura, porque não chegou à etapa de resposta HTTP.

Esses dados mostram atuação do rate limiter e erros ainda sem causa identificada. Não demonstram bypass nem permitem calcular de forma validada spillover e falsos positivos. Também não há séries salvas de CPU e memória correlacionadas com latência, nem acompanhamento independente de clientes legítimos durante essas execuções.”

**Transição:** “Com isso, a próxima etapa é transformar a geração de carga existente em um experimento de precisão alinhado ao TCC1.”

## 7. Próximas modificações propostas — 4 minutos

### Prioridade 1 — Definir exatamente o que será contado como erro

“Vou formalizar as fórmulas de spillover e falsos positivos, seus denominadores e a regra de admissão esperada por identidade. Essa referência precisa respeitar as janelas, rajadas e reposição de cada algoritmo. Uma resposta 429 não será automaticamente considerada falso positivo, e uma resposta 500 não será automaticamente considerada bypass.

Também vou tratar as diferenças entre gateways como hipóteses a verificar. O experimento não deve pressupor que a multiplexação necessariamente causa falhas.”

**Entrega verificável:** protocolo experimental com métricas, identidades, critérios de classificação e exemplos de requisições permitidas e rejeitadas.

### Prioridade 2 — Alinhar as configurações dos três gateways

“Vou padronizar o caminho até o backend, o escopo das identidades e os recursos disponíveis, documentando as diferenças que forem mantidas. Vou incluir Envoy no fluxo de testes e substituir a declaração genérica de equivalência por verificações de conformidade com cada política.

No Kong, preciso definir a estratégia efetivamente avaliada: o projeto menciona janela fixa e deslizante como candidatas, enquanto a configuração atual usa o plugin rate-limiting. A implementação final e o texto do projeto precisam descrever a mesma escolha.”

**Entrega verificável:** configurações versionadas e testes de contagem, limites de rajada, recuperação de capacidade e HTTP/2 para as variantes selecionadas.

### Prioridade 3 — Instrumentar e controlar a geração de carga

“Vou integrar a versão corrigida do gerador ao fluxo principal e usar identidades fixas no experimento de precisão. A rotação de identidade ficará em um cenário separado. Vou registrar timestamps mais precisos, identidade, protocolo negociado, conexões e streams, e correlacionar as requisições com a decisão do gateway e o recebimento no backend.

Também vou incluir um controle HTTP/1.1 com condições comparáveis para distinguir o efeito da multiplexação do efeito geral da carga concorrente.”

**Entrega verificável:** um ciclo completo em pelo menos um gateway, do envio da carga ao cálculo rastreável das duas métricas centrais do TCC.

### Prioridade 4 — Garantir saúde do alvo e observação sincronizada

“Antes da campanha, vou verificar os endpoints e explicar os erros 500. Durante os testes, vou coletar métricas do gateway e do backend, logs de encaminhamento e sondagens de clientes legítimos, incluindo períodos antes e depois da carga.

As métricas de precisão serão calculadas pelas decisões de admissão. CPU, memória e latência ajudarão a identificar gargalos e efeitos sobre a aplicação, além de apoiar a parte de reprodução do laboratório DDoS.”

**Entrega verificável:** execução com baseline saudável e arquivos de carga, logs e monitoramento vinculados pelo mesmo identificador de rodada.

### Prioridade 5 — Executar a campanha comparativa reproduzível

“Após validar esse ciclo, vou variar a concorrência de streams nos três gateways, com duração fixa, estado inicial controlado e repetições independentes. O TCC1 sugere, como exemplos, cinco minutos e trinta repetições por cenário; vou consolidar os valores da matriz após um piloto e alinhamento com o orientador.

Vou arquivar os dados brutos com comandos, commit, configurações, versões das imagens e recursos de hardware. A análise apresentará as métricas e sua variabilidade por cenário, sem tratar cada requisição de uma mesma execução como uma repetição independente.”

**Entrega verificável:** conjunto de execuções reproduzíveis e comparação estatística entre gateways, algoritmos e níveis de concorrência.

## 8. Encerramento e pedido de aprovação — 20 segundos

“O estágio atual é de laboratório funcional para geração e registro de carga, com validação básica de dois gateways. A medição de precisão prevista no TCC ainda precisa ser concluída.

Solicito sua aprovação para executar essas cinco modificações, começando pelo protocolo de medição e por um ciclo completo em um gateway. Podemos adotar a validação desse ciclo como marco para liberar a campanha comparativa de Kong, NGINX e Envoy?”

---

## Referências para consulta durante a reunião

- Projeto: [TCC1_Final_Isaias-Gabriel-Miranda-Sampaio.pdf](../../../TCC1_Final_Isaias-Gabriel-Miranda-Sampaio.pdf), seções 3–5.
- Inicialização: [Compose do laboratório](../../original_experiment/setup/docker-compose.yml), [start.sh](../../start.sh) e [run_lab.sh](../../original_experiment/run_lab.sh).
- Políticas: [Lua](../../original_experiment/setup/gateway/ratelimit.lua), [Kong](../../gateways/kong/kong.yml), [NGINX](../../gateways/nginx/nginx.conf) e [Envoy](../../gateways/envoy/envoy.yaml).
- Gerador corrigido: [algorithm5_http2_mux_fixed.go](../../original_experiment/attacks/algorithm5_http2_mux_fixed.go).
- Testes: [test_rate_limiting.py](../../tests/test_rate_limiting.py) e [comparison_report.py](../../tests/comparison_report.py).
- Evidências inspecionadas: [resultados das cargas](../../results) e [relatórios dos testes](../../tests/results).
