# Release 1.5 — Checkpoint P0-2 (Contact Workspace)

**Release:** 1.5
**Fase:** P0-2 — Contact Workspace
**Status:** APROVADO
**Commit:** `5ea29b2`
**Data:** 2026-07-22

## Progresso da iniciativa Contact Workspace / Intelligence

| Fase | Descrição | Status | Commit |
| --- | --- | --- | --- |
| P0-1 | — | ⚠️ Não identificado nesta iniciativa (ver nota abaixo) | — |
| P0-2 | Contact Workspace | ✅ Aprovado | `5ea29b2` |
| P0-3 | Contact Intelligence | ✅ Aprovado | `146eea9` |
| P0-4 | Recommendations (Action Center reuse) | ⏳ Pendente — aguardando proposta de arquitetura | — |

**Nota sobre P0-1:** não há, em nenhum lugar deste repositório ou desta
conversa, um "P0-1" pertencente a esta iniciativa (Contact Workspace/
Intelligence) — P0-2 é a primeira fase que de fato existe aqui. A única
ocorrência real de "P0-1" no repositório é um item completamente diferente
e não relacionado, já concluído há muito tempo: "fechar o auto-registro
aberto" (`ROADMAP_v1.1.md`, corrigido no commit `6b773c0`, ver
`RELEASE_1_3_1_POSTMORTEM.md`). Marcá-lo como "✅" aqui seria inventar uma
entrega que não existe nesta linha de trabalho — deixado como pendência de
esclarecimento em vez de uma marca fabricada.

## Resumo da funcionalidade entregue

Endpoint `GET /api/contacts/{contact_id}/workspace`: uma única leitura
agregada que reúne Notes/Tasks/Calendar/Messages/Memory já existentes em
torno de um contato, no formato `{ summary, timeline, current_state,
recommendations }`. Não é uma página de CRUD — cada bloco responde a uma
pergunta de relacionamento específica (quem é, quando falamos pela última
vez, o que está pendente, o que já foi discutido).

- **`timeline`**: merge cronológico de WhatsApp + Notas + Tarefas +
  Reuniões, um contrato estável por entrada (`id`, `type`, `timestamp`,
  `title`, `subtitle`, `status`, `source`, `metadata`), desempate
  determinístico por `(type, id)` em timestamps iguais, limite configurável
  via `Settings.contact_workspace_timeline_limit` (não mais uma constante
  fixa no código).
- **`current_state`**: tarefas abertas, próximos eventos, follow-ups
  pendentes, notas importantes.
- **`summary.relationship_status`/`suggested_next_action`**: reservados,
  `null` — propositalmente não computados nesta fase (ver P0-3 abaixo).
- **`recommendations`**: reservado, sempre `[]` — nada é fabricado aqui
  (ver P0-4 no roadmap).
- Migração `2cc4e7d820a6`: adiciona `contact_id` (nullable, indexado, `ON
  DELETE SET NULL`) em `tasks` e `calendar` — Notes já tinha. Ferramentas de
  agente (`agents/tools/productivity.py`) passam a vincular automaticamente
  tarefa/evento/nota criados durante uma conversa de WhatsApp ao contato
  daquela conversa.
- Frontend: `/contatos` (lista) e `/contatos/[id]` (workspace).

Arquivos: ver commit `5ea29b2` (15 arquivos, 1658 inserções — 4 arquivos
backend novos, 4 frontend novos, 7 modificados aditivamente).

## Resumo de validação

Todos os resultados abaixo foram verificados lendo o conteúdo real dos
logs gerados nesta rodada de validação — nenhum baseado em código de saída
de wrapper/notificação.

| Item | Resultado |
| --- | --- |
| Ruff (backend) | PASS — 0 problemas |
| Mypy (backend) | PASS COM DÉBITO PRÉ-EXISTENTE — 3 erros, nenhum nos 2 arquivos deste P0-2 (`api/contact_workspace.py`, `utils/config.py`) |
| Pytest (backend, suíte completa) | PASS — 1061 aprovados, 0 falhas |
| ESLint (frontend) | PASS — 0 problemas |
| TypeScript (frontend) | PASS — 0 erros |
| Vitest (frontend, suíte completa) | PASS — 323 aprovados, 0 falhas (rodada solo, sem concorrência de CPU) |
| Build de produção (frontend) | PASS — 34/34 rotas, nenhum aviso acionável |

Contagem de queries no endpoint: 6 consultas SQL reais por requisição, sem
N+1, sem consultas novas introduzidas pelas correções de contrato.

## Débito técnico conhecido (fora do escopo do P0-2)

- **Mypy**: `observability/operational_metrics.py` importa
  `opentelemetry.exporter.prometheus`, pacote não declarado em
  `requirements.txt` (só o exporter otlp-proto-http está). `admin/service.py`
  e `tests/test_admin.py` usam `psutil` sem stub instalado
  (`types-psutil` ausente de `requirements-dev.txt`). Nenhum dos três
  arquivos foi tocado por este branch — pré-existentes.
- **Working tree**: mudanças não commitadas e não relacionadas a este P0-2
  permanecem no repositório (`ROADMAP_v1_5.md`, `agents/tools/gdrive.py`,
  `providers/drive/*`, `docs/DRIVE.md`, `frontend/components/Sidebar.tsx`)
  — trabalho em andamento de outra frente (Google Drive), deliberadamente
  deixado de fora deste commit.

## Limitações conhecidas

- `summary.relationship_status` e `summary.suggested_next_action` seguem
  `null` — o contrato já está estável (frontend já renderiza um
  placeholder honesto), mas nenhum sinal é calculado ainda. É exatamente o
  objetivo do P0-3.
- `recommendations` segue sempre `[]` — reservado para P0-4.
- Não existe hoje nenhuma forma de responder "quais contatos precisam de
  atenção" **entre** contatos — o endpoint só enxerga um contato por vez.
  Também é objetivo do P0-3.
- `timeline` cobre só 4 fontes (WhatsApp/Notas/Tarefas/Reuniões); Email,
  Ligações, Documentos e CRM externo não existem como fonte ainda (o
  contrato foi desenhado para admitir isso sem quebra, mas nenhuma dessas
  fontes está implementada).
- Falha em `memory_manager.get_preferences`/`get_summary` (ex.: Qdrant
  fora do ar) é engolida silenciosamente (log de warning) — o endpoint
  nunca quebra por causa disso, mas também não expõe nenhum sinal de saúde
  dessa dependência na resposta.

## Próxima fase

**P0-3 — Contact Intelligence: CONCLUÍDO E APROVADO.** Commit `146eea9`.
`summary.relationship_status`/`suggested_next_action` deixaram de ser
`null` (backend/contacts/intelligence.py, deterministico, sem novas
queries); novo `GET /contacts/priority` para ranking entre contatos. Ver
`CONTACT_INTELLIGENCE_ARCHITECTURE.md` para o desenho completo e sua
seção "Architectural decision" (fronteira Intelligence vs. Action).

**P0-4 — Recommendations, pendente.** Ainda apenas uma proposta de
arquitetura será preparada (lifecycle de recomendação, fluxo de
confirmação, modelo de explicação, modelo de confiança, fronteira de
execução, trilha de auditoria) reaproveitando o Action Center/Planner já
existentes — nenhuma implementação, migração, endpoint ou componente de
frontend até aprovação explícita.
