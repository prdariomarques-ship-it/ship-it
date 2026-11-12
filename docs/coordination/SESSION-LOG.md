# Histórico de sessões (append-only)

Formato: data/hora (São Paulo) · sessão · evento · evidência · resultado · próxima ação. Registros corrigidos não são apagados: um novo registro aponta o anterior.

| Data/hora | Sessão | Evento | Evidência | Resultado | Próxima ação |
|---|---|---|---|---|---|
| 2026-11-12 ~10:00 | Memória cumulativa | Congelamento da cópia de homologação; fotografia independente. | Manifesto SHA-256 (1.525 arquivos). | Congelado e conferido. | — |
| 2026-11-12 ~12:20 | Memória cumulativa | Correção de deadlock/liveness no PostgreSQL 16 (lock por escopo, tratamento de conflito transitório). | Suíte relatada 2.411 ok / 0 falhas. | Relatado; módulo multiprocesso relatado 20/20. | Reverificar no estado atual. |
| 2026-11-12 ~13:00 | Memória cumulativa | Reconciliação de elegibilidade pós-commit portada para a cópia baseline. | Suíte completa executada sobre a cópia de trabalho: 2.444 ok / 0 falhas / 19 ignorados; manifesto 1.529 arquivos. | Verificado: 3 critérios de aceitação passam; teste de marca persistida segue falhando (fora de escopo). | Revisão formal do diff. |
| 2026-11-12 ~13:30 | Revisão independente | Revisão formal do diff da etapa 1. | Relatório somente leitura. | Achado ALTO H1: um dos leitores de resumo não passa pelo gate de reconciliação. Médios M1 a M5. | Correção autorizada (H1, M1, M2, M4). |
| 2026-11-12 ~14:00 | Coordenação | Autorização do responsável para corrigir H1, M1, M2 e M4; M3 e M5 adiados; marca persistida fora de escopo. | Mensagem do responsável. | Autorizado. | Implementar em cópia nova. |
| 2026-11-12 ~14:10 | Coordenação | Verificação das três verificações do porte pendentes na baseline. | Suíte na própria cópia baseline: 2.444 ok / 0 falhas / 19 ignorados; comparação por ID: 0 ausentes, 1 status alterado (para aprovado), 40 novos. | Verificado. | Revisão de diff. |
| 2026-11-12 ~14:20 | Implementação | H1 corrigido: gate de reconciliação passa a proteger também a leitura de `build_scoped_memories`. | Testes de H1: 20 falhavam antes; todos passam depois (SQLite e PG16). | Verificado. | — |
| 2026-11-12 ~14:25 | Implementação | M1 corrigido: escrita de epoch e de rótulo do ledger só sob a trava do escopo. | Testes de M1: reprovavam antes, passam depois. | Verificado. | — |
| 2026-11-12 ~14:40 | Implementação | M2 corrigido (reset idempotente sob concorrência) e M4 corrigido (rollback no gate e sessão própria do gate). | Testes direcionados: 82 aprovados em SQLite e PG16 [relatado]; lint: ruff ok, mypy só os 2 erros de stubs. | Relatado. | Validação final. |
| 2026-11-12 ~15:00 | Implementação | Suíte completa da cópia de reconciliação. | junit conferido: 2.494 ok / 0 falhas / 19 ignorados; comparação por ID com a baseline: 0 ausentes, 0 status alterado, 50 novos (24 H1, 10 M1, 8 M2, 8 M4). | Verificado. | Manifesto final e relatório. |
| 2026-11-12 ~15:10 | Implementação | Multiprocesso PG16 repetido 2 vezes (e não 3, como previsto). | Logs: 8 aprovados em cada execução. | Parcialmente cumprido. | Completar a terceira execução. |
| 2026-11-12 ~14:22 | Modelos e GPU | Retomada da rodada de seleção de modelos (controle Llama em execução). | Contêiner de inferência ativo; uso de GPU alto. | Verificado. | Decisão do responsável sobre retomada. |
| 2026-11-12 ~14:30 | Coordenação | Verificação do repositório público no GitHub. | Consulta somente leitura à API pública. | Repositório público; branch padrão `master`; commits `984b012…` e `36488bb…` **não encontrados** no GitHub (HTTP 422). | Decidir sobre publicação. |
