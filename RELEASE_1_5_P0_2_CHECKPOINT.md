# Release 1.5 — Checkpoint P0-2 (Contact Workspace)

**Release:** 1.5
**Fase:** P0-2 — Contact Workspace
**Status:** APROVADO
**Commit:** `5ea29b2`
**Data:** 2026-07-22

**Nota de fechamento (2026-07-23):** este checkpoint nasceu documentando
apenas o P0-2. As fases seguintes (P0-3, P0-4 e a rodada de hardening do
red-team audit) foram registradas abaixo, à medida que aconteceram, e a
iniciativa completa **Contact Workspace / Intelligence / Recommendations**
está concluída e selada no commit `108edf5`
(`feat(admin): complete Release 1.5 relationship workspace`). As seções
abaixo foram atualizadas nesta data para refletir esse estado final —
nenhuma referência a trabalho pendente de frontend, recomendações ou
auditoria permanece válida.

## Progresso da iniciativa Contact Workspace / Intelligence

| Fase | Descrição | Status | Commit |
| --- | --- | --- | --- |
| P0-1 | — | ⚠️ Não identificado nesta iniciativa (ver nota abaixo) | — |
| P0-2 | Contact Workspace | ✅ Aprovado | `5ea29b2` |
| P0-3 | Contact Intelligence | ✅ Aprovado | `146eea9` |
| P0-4 | Recommendations (Tool Registry reuse) — backend e frontend | ✅ Concluído e aprovado | `108edf5` |
| — | Hardening: achados do red-team audit (Contact Priority Panel / P0-4) | ✅ Concluído e aprovado | `108edf5` |

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
- **`summary.relationship_status`/`suggested_next_action`**: no P0-2
  original (`5ea29b2`) eram reservados e `null` — passaram a ser
  computados de fato no P0-3 (`146eea9`, ver abaixo).
- **`recommendations`**: no P0-2 original era reservado e sempre `[]` —
  passou a ser real no P0-4 (`108edf5`, ver "Estado final da iniciativa"
  abaixo).
- Migração `2cc4e7d820a6`: adiciona `contact_id` (nullable, indexado, `ON
  DELETE SET NULL`) em `tasks` e `calendar` — Notes já tinha. Ferramentas de
  agente (`agents/tools/productivity.py`) passam a vincular automaticamente
  tarefa/evento/nota criados durante uma conversa de WhatsApp ao contato
  daquela conversa.
- Frontend: `/contatos` (lista) e `/contatos/[id]` (workspace).

Arquivos do P0-2: ver commit `5ea29b2` (15 arquivos, 1658 inserções — 4
arquivos backend novos, 4 frontend novos, 7 modificados aditivamente).
Arquivos do P0-4 + hardening: ver commit `108edf5` (28 arquivos, 3011
inserções, 170 remoções).

## Estado final da iniciativa (P0-4 + hardening, commit `108edf5`)

**P0-4 — Recommendations: CONCLUÍDO E APROVADO**, backend e frontend.
`contacts/recommendations.py` (motor puro, sem dependência de banco/HTTP/
Tool Registry, `Recommendation` imutável) + `recommendations` real em
`GET /contacts/{id}/workspace` + `POST /contacts/{id}/recommendations/
{id}/execute` (revalida a recomendação a partir de dados vivos antes de
despachar — nunca confia no payload ecoado pelo cliente). Execução via
Tool Registry (`agents/tools/base.py::Tool.run`), nunca via Cognitive
Planner (avaliado e descartado explicitamente — ver
`P0_4_RECOMMENDATIONS_ARCHITECTURE.md`, "One correction before anything
else"). Escopo v1 deliberadamente restrito a dois tipos
(`follow_up`, `check_pending_tasks`), cada um rastreável a exatamente um
sinal do P0-3 — o restante do escopo aprovado (`SCHEDULE_MEETING`,
`SEND_WHATSAPP`, etc.) fica para uma iteração futura. Frontend
(`/contatos/[id]`, botão "Executar" por recomendação) e o **Contact
Priority Panel** (`GET /contacts/priority`, ranking entre contatos por
`priority_score`) foram construídos e estão em produção. Nav lateral
(`Sidebar.tsx`) ganhou o link "Contatos".

**Hardening — achados do red-team audit: CONCLUÍDO E APROVADO.** Seis
achados, todos resolvidos e cobertos por teste de regressão:

1. **Duplicate execution race** — guarda síncrona via `useRef<Set<string>>`
   em `handleExecute`, verificada antes de qualquer `await`; não depende de
   estado do React.
2. **Concurrent executions** — o guard e o estado de UI passaram de um
   escalar único (`executingId`) para um `Set<string>`, permitindo
   execuções independentes por recomendação.
3. **Localization** — `backend/utils/messages.py` centraliza as mensagens
   de erro voltadas ao usuário final em pt-BR; os 5 pontos de
   `HTTPException` em `contact_workspace.py` passam a usá-lo. Exceções e
   logs internos continuam em inglês (convenção do projeto).
4. **Navigation state** — estado local de execução/erro é resetado ao
   navegar entre contatos via ajuste de estado durante a renderização
   (não um `useEffect`, que violaria `react-hooks/set-state-in-effect`).
5. **Single Operator Constraint** — documentado como restrição
   arquitetural bloqueante em `docs/adr/ADR-0002-single-operator-
   constraint.md`, referenciada em `models/contact.py` e
   `docs/TECHNICAL_DEBT.md`. Nenhum código multi-usuário foi implementado.
6. **Business logic ownership** — seleção do "motivo primário" saiu do
   frontend (`ContactPriorityPanel.tsx`, que reimplementava sua própria
   ordenação por severidade) e passou a ser exclusivamente
   `contacts/intelligence.py::primary_risk_signal`; o frontend apenas
   renderiza o valor recebido.

**Correção adicional encontrada durante a validação final** (não fazia
parte da lista original de achados): `primary_risk_signal` retornava o
sinal de severidade "info" (`no_interaction_ever`) como "motivo primário",
o que o teste de regressão pegou (`test_primary_risk_signal_ignores_
opportunity_and_info_signals`). Corrigido isolando a seleção de sinal em
um helper compartilhado (`_highest_priority_signal`, com
`exclude_info=True/False`) para que `primary_risk_signal` e
`suggested_next_action` concordem em ordenação sem regredir o
comportamento já existente do segundo.

## Resumo de validação

Validação da entrega original do P0-2 (`5ea29b2`, 2026-07-22): todos os
resultados abaixo foram verificados lendo o conteúdo real dos logs
gerados naquela rodada — nenhum baseado em código de saída de
wrapper/notificação.

| Item | Resultado (P0-2, `5ea29b2`) |
| --- | --- |
| Ruff (backend) | PASS — 0 problemas |
| Mypy (backend) | PASS COM DÉBITO PRÉ-EXISTENTE — 3 erros, nenhum nos 2 arquivos deste P0-2 (`api/contact_workspace.py`, `utils/config.py`) |
| Pytest (backend, suíte completa) | PASS — 1061 aprovados, 0 falhas |
| ESLint (frontend) | PASS — 0 problemas |
| TypeScript (frontend) | PASS — 0 erros |
| Vitest (frontend, suíte completa) | PASS — 323 aprovados, 0 falhas (rodada solo, sem concorrência de CPU) |
| Build de produção (frontend) | PASS — 34/34 rotas, nenhum aviso acionável |

**Validação final da iniciativa completa** (P0-2 + P0-3 + P0-4 + hardening,
estado do commit `108edf5`, 2026-07-23):

| Item | Resultado (final, `108edf5`) |
| --- | --- |
| Ruff (backend) | PASS — 0 problemas |
| Mypy (backend) | PASS COM DÉBITO PRÉ-EXISTENTE — 3 erros, nenhum em arquivo tocado por esta iniciativa (ver "Débito técnico" abaixo) |
| Pytest (backend, suíte completa) | PASS — 1134 aprovados, 0 falhas |
| ESLint (frontend) | PASS — 0 problemas |
| TypeScript (frontend) | PASS — 0 erros |
| Vitest (frontend, suíte completa) | PASS — 329 aprovados, 0 falhas (48 arquivos de teste) |
| Build de produção (frontend) | PASS — 34/34 rotas |

Contagem de queries no endpoint (P0-2): 6 consultas SQL reais por
requisição, sem N+1, sem consultas novas introduzidas pelas correções de
contrato.

## Débito técnico conhecido (fora do escopo desta iniciativa)

- **Mypy**: `observability/operational_metrics.py` importa
  `opentelemetry.exporter.prometheus`, pacote não declarado em
  `requirements.txt` (só o exporter otlp-proto-http está). `admin/service.py`
  e `tests/test_admin.py` usam `psutil` sem stub instalado
  (`types-psutil` ausente de `requirements-dev.txt`). Nenhum dos três
  arquivos foi tocado por esta iniciativa — pré-existentes.
- **Working tree**: mudanças não commitadas e não relacionadas a esta
  iniciativa permanecem no repositório (`ROADMAP_v1_5.md`,
  `agents/tools/gdrive.py`, `providers/drive/*`, `docs/DRIVE.md`) —
  trabalho em andamento de outra frente (Google Drive: suporte a Google
  Docs/Sheets/Slides nativos), deliberadamente deixado de fora do commit
  `108edf5`. Um memorando de redirecionamento estratégico para a próxima
  iniciativa (`REDIRECIONAMENTO_RELEASE_1_5.md`, consolidação do
  Dashboard) também permanece não commitado, por ser planejamento futuro,
  não implementação.
- **Localização (Finding 3 do audit)**: `utils/messages.py` cobre
  deliberadamente só `api/contact_workspace.py`, onde o achado se
  originou — uma varredura completa do backend por mensagens de erro em
  inglês não foi feita e permanece como trabalho futuro (ver
  `docs/TECHNICAL_DEBT.md`).
- **Single Operator Constraint (Finding 5 do audit)**: documentada em
  `docs/adr/ADR-0002-single-operator-constraint.md` como restrição
  bloqueante, sem enforcement técnico (ex.: nenhum check em
  `POST /admin/users` impede hoje a criação de um segundo usuário real) —
  depende de disciplina de processo até que o redesenho de propriedade de
  `Contact` seja feito.

## Limitações conhecidas

- `timeline` cobre só 4 fontes (WhatsApp/Notas/Tarefas/Reuniões); Email,
  Ligações, Documentos e CRM externo não existem como fonte ainda (o
  contrato foi desenhado para admitir isso sem quebra, mas nenhuma dessas
  fontes está implementada).
- Falha em `memory_manager.get_preferences`/`get_summary` (ex.: Qdrant
  fora do ar) é engolida silenciosamente (log de warning) — o endpoint
  nunca quebra por causa disso, mas também não expõe nenhum sinal de saúde
  dessa dependência na resposta.
- Escopo de Recommendations (P0-4) permanece deliberadamente restrito a
  dois tipos (`follow_up`, `check_pending_tasks`); `SCHEDULE_MEETING`,
  `SEND_WHATSAPP`, `UPDATE_CONTACT`, `READ_NOTES`, `REVIEW_RELATIONSHIP`
  seguem aprovados para iteração futura, não implementados.

**Limitações do P0-2 original já resolvidas** (mantidas aqui só para
rastreabilidade histórica — nenhuma delas é válida hoje): `summary.
relationship_status`/`suggested_next_action` sendo sempre `null` (resolvido
no P0-3, `146eea9`); `recommendations` sempre `[]` (resolvido no P0-4,
`108edf5`); ausência de ranking entre contatos (resolvido no P0-3 via
`GET /contacts/priority`, `146eea9`).

## Conclusão da iniciativa

**P0-3 — Contact Intelligence: CONCLUÍDO E APROVADO.** Commit `146eea9`.
`summary.relationship_status`/`suggested_next_action` deixaram de ser
`null` (backend/contacts/intelligence.py, deterministico, sem novas
queries); novo `GET /contacts/priority` para ranking entre contatos. Ver
`CONTACT_INTELLIGENCE_ARCHITECTURE.md` para o desenho completo e sua
seção "Architectural decision" (fronteira Intelligence vs. Action).

**P0-4 — Recommendations: CONCLUÍDO E APROVADO.** Commit `108edf5` (ver
"Estado final da iniciativa" acima para o detalhamento completo).

**Hardening — red-team audit: CONCLUÍDO E APROVADO.** Commit `108edf5`.
Seis achados resolvidos, cobertos por teste de regressão, sem código
multi-usuário implementado (ver `docs/adr/ADR-0002-single-operator-
constraint.md`) e sem lógica de negócio remanescente no frontend.

A iniciativa **Contact Workspace / Intelligence / Recommendations** está
encerrada nesta release. Trabalho futuro (Google Drive nativo,
consolidação do Dashboard) segue em branches/documentos separados, fora
do escopo deste checkpoint.
