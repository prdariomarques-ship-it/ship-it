# Sprint v1.2.1 — Preparation Report

Tarefa exclusivamente de planejamento. Nenhum código, teste ou documento
existente foi alterado; nenhum commit foi feito. Os três arquivos gerados
por esta tarefa (`SPRINT_v1.2.1_BACKLOG.md`, `SPRINT_v1.2.1_PLAN.md`, e
este relatório) permanecem **não commitados**, como instruído.

## Resumo executivo

A v1.2.0 está oficialmente encerrada e documentada (`POST_RELEASE_REPORT.md`,
commit `d2ffc8a`). Esta tarefa validou, diretamente no código da branch
`master` — não confiando em nenhuma documentação prévia —, se os bugs e
gaps conhecidos ainda existem, encontrou um achado novo (uma inconsistência
cosmética no README) e não encontrou nenhum bug de severidade alta em
aberto. O backlog real de v1.2.1 é pequeno: uma vulnerabilidade de
segurança (CSP/HSTS ausentes) com complexidade compatível com um patch
release, e um item trivial de documentação.

**Não existem, nesta consolidação, documentos de laboratório sobre P0**
(`P0_VALIDATION_REPORT.md`, `ENGINEERING_BACKLOG.md`,
`IMPLEMENTATION_ORDER.md`, `RFC_v1.2.1.md`, `SECURITY_REVIEW.md`,
`ENGINEERING_ESTIMATE.md`, `IMPLEMENTATION_SEQUENCE.md`) — os sete
arquivos citados na Fase 2 da tarefa foram procurados na raiz do
repositório e não existem. A validação de P0 desta tarefa, portanto, usa
como candidatos os itens já documentados no próprio projeto
(`TECHNICAL_DEBT.md`, `KNOWN_LIMITATIONS.md`, `SPRINT5_REPORT.md`), cada
um reverificado agora, do zero, contra o código real.

## Validação dos P0

Cada item abaixo foi verificado lendo o arquivo real na branch `master`
(não a documentação) nesta sessão.

| # | Item | Status | Arquivo | Função/local | Linha aprox. |
|---|---|---|---|---|---|
| 1 | `MemoryService.search()` chamava `AsyncQdrantClient.search()`, removido no `qdrant-client` 1.18+ | **JÁ CORRIGIDO** | `backend/memory/service.py` | `MemoryService.search` | 90–116 (chamada em 103, usa `query_points`) |
| 2 | Login com credenciais erradas não mostrava erro (`apiFetch` redirecionava 401 anônimo para `/login`) | **JÁ CORRIGIDO** | `frontend/hooks/useApi.ts` | `apiFetch` | 69 (`&& token` adicionado à condição) |
| 3 | `favicon.ico` ausente (404 em toda página) | **JÁ CORRIGIDO** | `frontend/app/favicon.ico` | — (arquivo existe, ICO 32×32 válido) | — |
| 4 | 3 violações WCAG 2 AA de contraste + 1 região rolável sem foco por teclado | **JÁ CORRIGIDO** | `frontend/styles/globals.css`, `frontend/styles/admin.css`, `frontend/components/admin/AdminShell.tsx` | cor `.sidebar a.active`; `--admin-primary`/`--admin-destructive`; `<main tabIndex>` | globals.css:71; admin.css:22,39; AdminShell.tsx:42 |
| 5 | Overflow horizontal em mobile (sidebar sem media query) | **JÁ CORRIGIDO** | `frontend/styles/globals.css` | media query `@media (max-width: 860px)` | 85 |
| 6 | CSP e HSTS ausentes no Caddyfile | **CONFIRMADO** (ainda em aberto) | `docker/caddy/Caddyfile` | bloco `header {}` | 5–10 |
| 7 | CVEs em `next@14.2.21`/`postcss` | **CONFIRMADO** (ainda em aberto) | `frontend/package.json` | dependência `next` | 29 (reconfirmado via `npm audit`, 1 crítica + várias altas) |
| 8 | Sem retry/backoff nos 4 providers Google | **CONFIRMADO** (real, mas fora do escopo v1.2.1 — v1.3.0) | `providers/mail/gmail/`, `providers/calendar/google/`, `providers/contacts/google/`, `providers/drive/google/` | qualquer `provider.py` dos quatro | zero ocorrências de retry/backoff, contra `providers/whatsapp/base.py:143-153` que tem |
| 9 | Sem circuit breaker / `Retry-After` / bulkhead | **CONFIRMADO** (fora do escopo v1.2.1 — v1.3.0) | mesmos 4 providers acima | — | — |
| 10 | Backup do Qdrant não automatizado | **CONFIRMADO** (real, sem versão-alvo) | `scripts/backup.sh` | script inteiro | 1–19 (só `pg_dump`) |
| 11 | Sem tabela de auditoria de execução por agente/tool | **CONFIRMADO** (decisão de escopo, não bug) | `backend/admin/router.py` | `admin_executions` | 305–315 (docstring confirma) |
| 12 | QR Code do WhatsApp não implementado | **CONFIRMADO** (decisão de escopo, não bug) | `backend/providers/whatsapp/` | — | zero ocorrências de `qr_code`/`get_qr`/`qrcode` |
| 13 | *(novo, encontrado nesta auditoria)* Contagem de testes divergente dentro do próprio README | **CONFIRMADO** (novo achado) | `README.md` | árvore de diretórios / seção Desenvolvimento | 103 (`473 testes`) vs. 317 (`555 testes`) |

**Controle positivo** (verificado para garantir que nenhuma regressão de
segurança escapou): `backend/main.py`, função
`_validate_production_settings` (linhas 74–95), continua recusando subir
em produção com `JWT_SECRET`/`WEBHOOK_SECRET` fraco ou ausente — nenhuma
regressão encontrada em PROD-004. Nenhuma credencial hardcoded encontrada
em varredura fresca de `backend/` e `frontend/` (padrões de chave OpenAI/
Google/chave privada).

Nenhum item foi classificado como **PARCIALMENTE CONFIRMADO** ou **NÃO
REPRODUZIDO** — todos os candidatos verificados tinham evidência direta e
inequívoca no código, em um sentido ou outro.

## Achados por grupo

Ver `SPRINT_v1.2.1_BACKLOG.md` para a versão completa com prioridade,
impacto, complexidade, estimativa, dependências e risco por item.

- **BUGS**: 1 (P3, trivial — inconsistência de contagem no README).
- **VULNERABILIDADES**: 2 (CSP/HSTS ausentes — dentro do escopo v1.2.1;
  CVEs do Next.js — fora do escopo, exige upgrade major).
- **DÍVIDAS TÉCNICAS**: 7 (retry Google, circuit breaker/Retry-After/
  bulkhead, backup do Qdrant, auditoria de execução, QR Code, Lighthouse,
  mypy) — nenhuma dentro do escopo de v1.2.1.
- **MELHORIAS ARQUITETURAIS**: 8 (Scheduler, Alertas, visibilidade de
  fila, Multi-Agent, Planning, Autonomous Execution, Self Healing, Memory
  Evolution) — todas v1.4.0/v2.0.0, fora do escopo por definição.

## Backlog oficial

Ver `SPRINT_v1.2.1_BACKLOG.md`. Dois itens dentro do escopo de v1.2.1:
**VULN-1** (CSP/HSTS, P1) e **BUG-1** (README, P3).

## Plano da Sprint

Ver `SPRINT_v1.2.1_PLAN.md`: objetivo, escopo dentro/fora, estratégia de
implementação em duas etapas para VULN-1 (HSTS primeiro, CSP em
`Report-Only` antes de efetiva), estratégia de rollback (toda mudança
desta sprint é configuração de borda ou texto, nenhuma tem estado
persistente envolvido), plano de testes (suíte completa + observação em
staging antes de promover a CSP) e critérios de aceite.

## Checklist de preparação

- [x] Fase 1 — documentação completa lida (9 arquivos)
- [x] Fase 2 — documentos de laboratório sobre P0 verificados (nenhum
      existe; documentado explicitamente, não presumido)
- [x] Fase 3 — 13 candidatos a P0 validados diretamente no código, com
      arquivo/função/linha para cada um
- [x] Fase 4 — achados separados em 4 grupos (Bugs, Vulnerabilidades,
      Dívidas Técnicas, Melhorias Arquiteturais)
- [x] Fase 5 — `SPRINT_v1.2.1_BACKLOG.md` gerado
- [x] Fase 6 — `SPRINT_v1.2.1_PLAN.md` gerado
- [x] Fase 7 — validação final executada (somente leitura)

## Resultado da validação final (Fase 7)

| Validação | Resultado |
|---|---|
| `git status` | ✅ Limpo (só os 3 arquivos desta tarefa, não commitados) |
| TypeScript (`tsc --noEmit`) | ✅ 0 erros |
| ESLint | ✅ 0 erros/warnings |
| Ruff | ✅ All checks passed |
| Pytest | ✅ 555 passed |
| Frontend Tests (Vitest) | ✅ 108 passed |
| Playwright (E2E) | ✅ 23 passed (duas execuções anteriores tiveram flakes transientes de cold-start do dev server do Next.js — mesmo padrão já documentado em `SPRINT5_REPORT.md`; terceira execução, limpa, confirmou 23/23 sem nenhum código alterado entre as tentativas) |
| Build de produção (Next.js) | ✅ sucesso |
| `docker compose config` | ✅ válido |

Nenhum código, teste ou documentação existente foi modificado durante
esta tarefa — confirmado pelo `git status` acima, que só lista os 3
arquivos novos desta preparação (nenhum arquivo pré-existente aparece
como modificado).

## Veredito

**A Sprint v1.2.1 está pronta para implementação.**

O escopo é deliberadamente pequeno — um único item de complexidade real
(CSP/HSTS) e um item trivial de documentação — porque a verificação
direta no código não encontrou nenhum bug de severidade alta em aberto na
branch `master`: os 5 bugs conhecidos da v1.2.0 estão genuinamente
corrigidos, e nenhum bug novo foi descoberto nesta auditoria. Isso é
consistente com o próprio `ROADMAP_v2.md`, que já reservava v1.2.1
exclusivamente para esse cenário. A implementação pode começar com risco
mínimo seguindo `SPRINT_v1.2.1_PLAN.md`.
