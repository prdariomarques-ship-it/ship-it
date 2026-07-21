# Dario OS v1.4 — Notas de Release

**Data:** 2026-07-21

Ciclo predominantemente funcional (ao contrário do v1.3.1, que foi
hardening/débito técnico): os 6 itens Must/Should Have do `ROADMAP_v1_5.md`
foram entregues, mais 3 itens adicionais fora desse roadmap original
(busca semântica de memória, módulo de Notas dedicado, busca em
Contacts/Church). Nenhuma mudança de arquitetura além do estritamente
necessário para cada funcionalidade — todo o trabalho reaproveita padrões
já estabelecidos (Strategy+Factory, CRUD genérico, fila de jobs, audit
log, Event Bus). Auditoria completa de release: ver `RELEASE_1_4_POSTMORTEM.md`.

## Novidades

- **GoalManager: edição, cancelamento, progresso, dependências e histórico**
  (`/metas`). A UI de Metas só criava e aprovava — agora cobre o CRUD
  completo. Commit `6583a43`.
- **Busca semântica de memória exposta em `/admin/memory`**. O endpoint
  `GET /memory/search` já existia e funcionava; o painel admin só mostrava
  estatísticas da coleção Qdrant, sem forma de consultá-la. Commit `a15ddb0`.
- **Fluxo de "esqueci minha senha"**. Modelo de entrega: o admin gera um
  token (`POST /admin/users/{id}/password-reset-token`, retornado uma
  única vez) e repassa fora de banda (WhatsApp, verbalmente) — sem SMTP/SMS
  configurado neste projeto. Nunca loga o token. Rate limiting dedicado em
  `/auth/forgot-password` (por e-mail) e `/auth/reset-password` (por IP).
  Piso de tempo constante (100ms) para a branch "e-mail não encontrado" não
  ser distinguível da branch "encontrado" por tempo de resposta. Páginas
  `/esqueci-senha` e `/redefinir-senha`. Commits `e2e4d99`, `393bac9`.
- **QR Code do WhatsApp no Dashboard Administrativo** (`/admin/whatsapp`).
  Link direto para a página de pareamento do próprio openwa (não existe
  endpoint REST de QR — confirmado contra o gateway real). Novo campo
  `OPENWA_PUBLIC_QR_URL`. Commit `cb8632a`.
- **Módulo de Notas dedicado** (`notas/`), substituindo o CRUD genérico
  anterior: busca, `pinned`/`archived`, `contact_id` reservado para uso
  futuro (vínculo Nota↔Contato, ainda não implementado). Arquitetura
  documentada para "AI readiness" futura (embeddings, resumo por IA) sem
  implementá-la ainda. Commit `a17237a`.
- **Busca por nome em Contacts e Church** (`?q=`) — os repositórios já
  tinham `search_by_name`; exposta via um parâmetro novo (`repository_cls`)
  no factory genérico de CRUD (`api/crud.py`), reaproveitado por ambos os
  domínios sem duplicar rota. UI de busca adicionada em `/igreja` (Contacts
  não tem página dedicada no frontend). Commit `7997634`.
- **Gmail: capacidade de resposta** (`reply_to_email_thread`). Deliberadamente
  só resposta dentro de uma conversa existente — nunca compor e-mail novo
  para endereço arbitrário (mesmo princípio de isolamento do WhatsApp,
  PROD-005). Destinatário sempre resolvido do remetente da última mensagem
  da própria thread. Envio via fila de jobs durável. Escopo `gmail.send`
  adicionado — contas conectadas antes desta mudança precisam reconectar.
  Commit `08e7895`.
- **Google Calendar: edição de série recorrente**. Criar eventos com
  `recurrence` (RRULE); editar/excluir com `scope="this_event"` (padrão,
  só a ocorrência) ou `scope="all_events"` (a série inteira, resolvida pro
  evento mestre via um novo método interno do Strategy, `get_event`). "Este
  evento e os seguintes" deliberadamente fora do escopo (exigiria dividir a
  RRULE manualmente). Commits `19f8e82`, `c533ffa`.
- **Dashboard Settings: editável**. `/admin/settings` deixa de ser 100%
  somente leitura — `auto_reply_enabled` agora é editável, com efeito
  imediato (muta o singleton `Settings()` em memória) e persistência
  através de restarts (tabela nova `app_settings`, aplicada de volta no
  boot). `jobs_enabled`/`environment`/providers continuam somente leitura,
  por decisão de escopo explícita (ver `docs/DASHBOARD.md`). **Implementado
  e validado nesta auditoria; aguardando commit/push explícito do
  fundador antes de entrar no histórico do repositório** (ver
  `RELEASE_1_4_POSTMORTEM.md`).

## Correções de bugs

Nenhuma correção de bug isolada neste ciclo — o ciclo anterior (v1.3.1) já
havia fechado os incidentes de produção conhecidos. Um problema secundário
foi corrigido incidentalmente durante a validação do item de memória
semântica: `GoalDetails.test.tsx` tinha uma assinatura de mock de `fetch`
já inconsistente com a real (erro de tipo latente, nunca disparado).

## Melhorias de segurança

- Password reset nunca loga o token bruto — só audit trail sem dado
  sensível.
- Rate limiting dedicado (não o limitador global genérico) em
  `/auth/forgot-password` e `/auth/reset-password`.
- Piso de tempo constante no `request_password_reset` contra enumeração de
  e-mail por tempo de resposta.
- Escopo mínimo do Gmail ampliado de forma deliberada e documentada
  (`gmail.readonly` + `gmail.send`, nunca `gmail.modify`/`gmail.compose`).
- Nenhuma tool nova aceita destinatário/conta arbitrário do modelo — o
  princípio PROD-005 (isolamento decidido em código, nunca só por prompt)
  foi replicado consistentemente em Gmail e Calendar.
- Catálogo de configurações editáveis (`app_settings`) é uma allowlist
  fixa no código (`SETTINGS_CATALOG`) — não existe caminho para persistir
  ou editar uma chave fora dela; nenhum segredo passa por esse mecanismo.

## Melhorias operacionais

- `docs/EMAIL.md`, `docs/CALENDAR.md`, `docs/NOTES.md`, `docs/DASHBOARD.md`
  atualizados para refletir cada funcionalidade nova, incluindo seções
  dedicadas de limitação/escopo explícito.
- `ROADMAP_v1_4.md` ganhou uma nova seção de melhorias futuras do módulo de
  Notas (itens 17-26) e, na mesma seção, os itens 27-29 para Google
  Calendar (este e os seguintes / validação local de RRULE / UI
  dedicada de edição).

## Breaking changes

Nenhum. Todas as mudanças são aditivas — nenhum endpoint, schema ou
contrato existente foi removido ou alterado de forma incompatível. A única
mudança que exige ação do operador: contas Gmail conectadas antes desta
release precisam reconectar (botão "Reconnect" em `/admin/google`) para
conceder o novo escopo `gmail.send` antes que `reply_to_email_thread`
funcione — a leitura (`search`/`get_thread`/etc.) continua funcionando
normalmente sem reconectar.

## Notas de migração

- Nova migração Alembic `68ff6ab67cdd` (tabela `app_settings`) — aplicar
  `alembic upgrade head` antes de subir esta versão. Migração puramente
  aditiva (`CREATE TABLE`), sem risco de dado existente.
- Duas migrações adicionais deste ciclo já aplicadas ao longo do
  desenvolvimento: `389bdd08a97f` (password_reset_tokens) e `a1f9c3d84e2b`
  (colunas `pinned`/`archived`/`contact_id` em `notes`).
- Sem mudança de variável de ambiente obrigatória — `OPENWA_PUBLIC_QR_URL`
  é opcional (sem ela, o link de QR simplesmente não aparece).

## Problemas conhecidos

- Nenhum bloqueante encontrado na certificação final (ver
  `RELEASE_1_4_POSTMORTEM.md`, seção "Problemas remanescentes conhecidos").
- `/auth/login` depende só do limitador de taxa genérico (120 req/min/IP),
  sem um freio dedicado contra força bruta como o de forgot/reset-password
  — pré-existente, não introduzido neste ciclo.
- Ver `TECHNICAL_DEBT.md` para a lista completa de itens não-bloqueantes.
