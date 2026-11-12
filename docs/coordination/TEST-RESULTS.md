# Resultados de testes

Banco: PostgreSQL 16 e SQLite, cada teste roda nos dois quando aplicável. Os números abaixo vêm de arquivos de resultado (junit) conferidos por esta coordenação, salvo indicação.

## Suítes completas
| Cópia | Data | Aprovados | Falhas | Ignorados | IDs | Origem |
|---|---|---|---|---|---|---|
| Baseline `candidate-agent-memory-ledger-v1` (pós-elegibilidade) | 2026-11-12 | 2.444 | 0 | 19 | 2.463 | executada na própria cópia, conferida |
| Implementação H1/M1/M2/M4 | 2026-11-12 | 2.494 | 0 | 19 | 2.513 | executada pela sessão de implementação; junit conferido |
| Referência histórica (auditoria pré-correções) | 2026-11-12 | 2.403 | 1 | 19 | 2.423 | executada; ID com falha: multiprocesso `[5]` |

Os 19 ignorados são testes DARIUS, que exigem um checkout externo não disponível nesta missão. São **não verificados**.

## Comparação por identificador (implementação × baseline)
- IDs da baseline ausentes na implementação: **0**.
- IDs com mudança de status: **0**.
- IDs novos: **50** = 24 (H1) + 10 (M1) + 8 (M2) + 8 (M4).
- Lista completa: `ids_novos_final.txt` (arquivo local, fora deste repositório).

## Testes direcionados
- H1, M1, M2, M4 e reconciliação: 82 aprovados em SQLite e PG16 (relatado pela sessão de implementação).
- Multiprocesso PG16 (8 testes): 8/8 em duas execuções (`run_final_mp1`, `run_final_mp2`). **A terceira execução prevista ainda não foi feita.**

## Qualidade estática
- Ruff: limpo.
- Mypy: 2 erros, preexistentes, de stubs `yaml` (sem stubs instalados). Sem regressão.

## Pendências de teste
- Terceira execução do multiprocesso.
- Revisão do diff pela sessão de revisão.
- Teste de marca persistida (`test_watermark_converges…`) falha na baseline e continua fora de escopo.
- Testes DARIUS (19): sem checkout externo autorizado.
