# Central de documentação e estudos

Se você está chegando agora, leia o **[roteiro de estudos](study/STUDY_PLAN.md)** e o **[mapa da aplicação](study/APPLICATION_MAP.md)**. Não é necessário ler todos os arquivos em sequência.

O projeto estuda a precisão do rate limiting em gateways à frente do Sock Shop. Há também uma trilha anterior de reprodução de algoritmos de geração de carga. A organização abaixo separa essas finalidades.

## Leitura principal

| Material | Para que serve |
|---|---|
| [Roteiro de estudos](study/STUDY_PLAN.md) | Oito sessões com leituras, exercícios e critérios de avanço |
| [Mapa da aplicação](study/APPLICATION_MAP.md) | Arquitetura, fluxo das requisições e ordem de leitura do código |
| [Diário de estudos](study/STUDY_JOURNAL.md) | Registrar entendimento, dúvidas e próximo passo |
| [Estado consolidado](status/CURRENT_STATUS.md) | Último resumo experimental registrado, de 16/10/2026 |
| [Protocolo experimental](methodology/EXPERIMENTAL_PROTOCOL.md) | Como medir e quais decisões ainda estão pendentes |

## Evidências registradas

A [validação funcional de 20/10/2026](reports/GATEWAY_VALIDATION_2026-10-20.md) verificou os três gateways após a reorganização: 15 testes aprovados, carga HTTP/2 limitada e recuperação. Essa regressão é separada da campanha experimental de precisão.

Leia nesta ordem: [piloto HTTP/1.1](reports/KONG_PILOT_2026-10-16.md), [auditoria operacional](reports/OPERATIONAL_AUDIT_2026-10-16.md) e [diagnóstico HTTP/2 após reinício](reports/RESTART_LOAD_REPORT_2026-10-16.md). São registros datados, não uma garantia de que os containers estejam ativos hoje.

## Consulta técnica e material anterior

A reprodução do artigo está isolada em [original_experiment/](../original_experiment/README.md), incluindo scripts, setup, guias e resultados. Sua leitura é opcional para estudar o experimento atual.

| Tema | Documentação |
|---|---|
| Laboratório e lançadores | [README do experimento atual](../README.md) |
| Gateways intercambiáveis | [Kong](../gateways/kong/README.md), [NGINX](../gateways/nginx/README.md), [Envoy](../gateways/envoy/README.md) |
| Laboratório OpenResty/Lua | [Setup](../original_experiment/setup/README.md) |
| Reprodução da trilha do artigo | [Walkthrough](../original_experiment/docs/WALKTHROUGH.md) |
| Monitoramento | [Guia](../original_experiment/docs/MONITORING.md), [anotações do monitor rápido](../original_experiment/docs/monitor_fast.md) |
| Gerador HTTP/2 antigo | [Explicação do algoritmo 5](../original_experiment/docs/algorithm5_http2_mux.md) |
| Apresentação | [Roteiro para o orientador](presentations/ADVISOR_PRESENTATION_OUTLINE.md) |
| Histórico | [Estado de 06/10](history/APPLICATION_STATUS_2026-10-06.md), [resumo anterior para avaliação](history/SUMMARY_FOR_AI_EVALUATION.md) |
| Organização | [Localização anterior e atual dos arquivos](DOCUMENTATION_STRUCTURE.md) |

Os guias antigos contêm afirmações que exigem revisão: o setup executa OpenResty/Lua, não Spring Cloud Gateway; limites nominais iguais não tornam Kong e NGINX matematicamente equivalentes; respostas 429 não demonstram, isoladamente, indisponibilidade. Use o mapa da aplicação e o protocolo como contexto antes de reproduzir comandos.
