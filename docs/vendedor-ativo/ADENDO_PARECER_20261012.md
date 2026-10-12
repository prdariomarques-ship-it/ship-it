# Adendo — correções do parecer de 12/10/2026

Base: `5372c27` (`chore/next-16.4-security`). Série anterior: 7 commits até `7198e7d`. Este adendo vem em commit(s) **posteriores, locais, não publicados**. Nada foi implantado, ativado ou enviado. A branch `feat/vendedor-ativo-voz` no GitHub continua com os 7 commits ANTERIORES às correções.

| Achado | Correção | Prova (teste) |
|---|---|---|
| P1 acompanhamento enfileirado ignora recusa posterior | `reserve_plain_send(..., guard=)` roda uma conferência sob a trava da conversa, antes da reserva; `store_followups.send_guard` revalida opt-out/recusa, habilitação, horário confirmado, janela com relógio de agora, identidade do job, tentativa, origem e texto (fatos). Bloqueio cancela (persistente) ou adia sem gastar tentativa. Payload de acompanhamento sem identidade de job falha fechado. A voz do acompanhamento obedece à mesma decisão (opt-out, recusa, janela). | `test_parecer_vendedor_ativo.py` (worker real; zero chamadas ao provedor) |
| P1 dois processadores, dois jobs | claim atômico (UPDATE condicional em estado+tentativa) na mesma transação que cria o job; identidade de envio estável `followup-send:<id>:<tentativa>` | `test_followup_claim_postgres.py` — **PostgreSQL 16 real, duas/três sessões com barreira após a seleção: 1 job, 1 chamada ao provedor** |
| P2 pedido de áudio vira recusa | regex separada: negativo exige negação; afirmativo → `reply_mode=audio`, limpa `voice_opt_out`; nunca reverte opt-out de contatos | classificação + handler real |
| P2 roteiro > limite do serviço | `STORE_VOICE_MAX_SCRIPT_CHARS` agora é o limite do roteiro FINAL (340 < 350); o resumo encolhe, o aviso nunca sai; sem espaço → sem áudio | exemplo do parecer (422 → ≤340), varredura de tamanhos, contrato real simulado (413) |
| P2 horário provisório como fato | `STORE_HOURS_CONFIRMED=false` por padrão: resposta qualificada, `aberto_agora=None`, nenhum acompanhamento planejado/enviado/aplicado | testes da ferramenta, planner, `run_due`, guard |
| P2 margem negativa; consulta por data com "agora" ao meio-dia; fuso | validação 0–240 e de fuso na carga; consulta por data devolve só o horário do dia | testes de configuração e da ferramenta |
| P2 resposta nova entre conferência e reserva (voz) | a mesma conferência roda dentro da reserva (guard sob a trava); o opt-out também toma a trava | teste que injeta a resposta imediatamente antes da reserva real; PG: reserva em andamento segura o opt-out |
| Download sem limite | leitura em fluxo com limite acumulado, com e sem Content-Length; metadados limitados a 64 KB | testes de corpo excessivo |
| Promessa "idêntico ao atual" | corrigida em `IMPLANTACAO_E_REVERSAO.md` (o que muda mesmo com as chaves desligadas) | — |

Achado adicional (meu): o caminho `reserva != reserved` em `store_voice.deliver` lia `row.id` após `rollback()` (atributo expirado → erro em async); corrigido e coberto.

## Resultados (separados)
- **Suíte do backend em SQLite:** 1454 passed, 5 skipped, 0 falhas (saída em `saidas/`). Antes das correções: 1374.
- **Concorrência em PostgreSQL 16 descartável** (127.0.0.1, banco recriado a cada teste, removido depois): 5 testes passam; sem `TEST_POSTGRES_URL` são pulados.
- **Mutantes:** 28 mutantes das correções, 28 mortos (3 exigiram reforço de teste: identidade do job, guard ignorado, trava do opt-out).
- ruff limpo; mypy 12 erros pré-existentes, nenhum novo.

## Continua pendente (inalterado)
Amostras e medições com modelo real; licença dos pesos; versão do Evolution e reprodução como voz; migração na cadeia de produção e unificação com PR #63/FH4; `store_agent.py` de produção; pós-venda por voz; revisão humana antes de qualquer publicação/implantação.
