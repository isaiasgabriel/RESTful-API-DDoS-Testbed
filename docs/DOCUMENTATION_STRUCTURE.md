# Organização da documentação

Reorganização em 20/10/2026. Os textos existentes foram preservados com ajustes de navegação e notas de contexto; não representam nova execução dos experimentos.

A pasta `lab/docs/` pertence ao repositório Git de `lab/`. PDFs, slides e código continuam em suas pastas. READMEs de componentes permanecem junto às configurações. Dados em `lab/results/` continuam separados e podem ser ignorados pelo Git; precisam de backup próprio.

## Onde cada documento foi parar

Caminhos relativos à pasta `ddos/`:

| Antes | Agora |
|---|---|
| `CURRENT_STATUS.md` | [lab/docs/status/CURRENT_STATUS.md](status/CURRENT_STATUS.md) |
| `EXPERIMENTAL_PROTOCOL.md` | [lab/docs/methodology/EXPERIMENTAL_PROTOCOL.md](methodology/EXPERIMENTAL_PROTOCOL.md) |
| `APPLICATION_STATUS_2026-10-06.md` | [lab/docs/history/APPLICATION_STATUS_2026-10-06.md](history/APPLICATION_STATUS_2026-10-06.md) |
| `SUMMARY_FOR_AI_EVALUATION.md` | [lab/docs/history/SUMMARY_FOR_AI_EVALUATION.md](history/SUMMARY_FOR_AI_EVALUATION.md) |
| `ADVISOR_PRESENTATION_OUTLINE.md` | [lab/docs/presentations/ADVISOR_PRESENTATION_OUTLINE.md](presentations/ADVISOR_PRESENTATION_OUTLINE.md) |
| `OPERATIONAL_AUDIT_2026-10-16.md` | [lab/docs/reports/OPERATIONAL_AUDIT_2026-10-16.md](reports/OPERATIONAL_AUDIT_2026-10-16.md) |
| `RESTART_LOAD_REPORT_2026-10-16.md` | [lab/docs/reports/RESTART_LOAD_REPORT_2026-10-16.md](reports/RESTART_LOAD_REPORT_2026-10-16.md) |
| `lab/KONG_PILOT_2026-10-16.md` | [lab/docs/reports/KONG_PILOT_2026-10-16.md](reports/KONG_PILOT_2026-10-16.md) |
| `lab/WALKTHROUGH.md` | [lab/original_experiment/docs/WALKTHROUGH.md](../original_experiment/docs/WALKTHROUGH.md) |
| `lab/MONITORING.md` | [lab/original_experiment/docs/MONITORING.md](../original_experiment/docs/MONITORING.md) |
| `lab/attacks/algorithm5_http2_mux.md` | [lab/original_experiment/docs/algorithm5_http2_mux.md](../original_experiment/docs/algorithm5_http2_mux.md) |
| `lab/monitoring/monitor_fast.md` | [lab/original_experiment/docs/monitor_fast.md](../original_experiment/docs/monitor_fast.md) |

## Como manter

- Comece sempre pelo [índice](README.md); adicione ali novos materiais.
- Atualize `status/CURRENT_STATUS.md` com data e links para evidências.
- Registre decisões de medição em `methodology/`; resultados datados em `reports/`.
- Guarde retratos superados em `history/`, sem apresentá-los como estado atual.
- Use `study/STUDY_JOURNAL.md` para dúvidas e progresso.
- Preserve nos guias o diretório de execução dos comandos.
- O arquivo `instructions` na raiz é uma anotação antiga de sessão, não o ponto de entrada do projeto.

O gerador `generate_slides.py` foi ajustado para ler o roteiro no novo caminho. Links para PDFs acima de `lab/` dependem da estrutura local completa; um clone apenas de `lab/` não inclui esses materiais.

## Separação dos experimentos

A reprodução do artigo passou para `lab/original_experiment/`, dentro do mesmo repositório Git. Foram movidos `algorithms/`, `attacks/`, `setup/`, `monitoring/`, `attack_cli.py`, `run_lab.sh` e a sondagem `rate_limit_test.sh` da raiz superior. Os guias antes em `docs/guides/` e o README técnico anterior estão em `original_experiment/docs/`.

Os arquivos `endpoints.json`, `targets.json` e os CSVs históricos `h2mux*` foram movidos de `lab/results/` para `lab/original_experiment/results/`, preservando o conteúdo. As auditorias, o piloto Kong e o diagnóstico recente continuam em `lab/results/`. Caminhos registrados dentro de artefatos históricos não foram reescritos.

O README principal agora descreve apenas a entrada do experimento atual. Cada trilha tem seu próprio `requirements.txt`; os algoritmos e as configurações de execução foram preservados. As referências dos documentos foram atualizadas, mas trechos narrativos históricos podem mencionar a organização da época.

Essa separação é de código e documentação: as duas composições continuam compartilhando portas e nomes de containers, portanto não devem rodar simultaneamente.

Durante a verificação da separação, `pytest --collect-only` revelou um hook que sobrescrevia o relatório NGINX mesmo sem executar testes. O hook foi corrigido. O relatório foi recomposto com status e latências do comparativo histórico preservado (exitstatus 0 inferido); a recuperação está registrada em `lab/tests/results/nginx_report_recovery.txt`. Não representa nova medição.

## Naming convention

Use English names for files and directories. Keep directory names in lowercase, with underscores for multiple words (for example, `original_experiment/`). Use uppercase descriptive names for Markdown guides (for example, `STUDY_PLAN.md`) and retain ISO dates in dated reports. Document content may remain in Portuguese. Update links, scripts and output paths whenever files move.

The slide generator is now `generate_slides.py`; its output directory is `presentations/` and its output basename is `TCC_Lab_Status`. Existing presentation files were renamed without regenerating their contents.
