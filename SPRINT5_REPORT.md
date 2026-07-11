# Sprint 5 — Production Hardening — Relatório Final

## Resumo executivo

Sprint exclusivamente de produção, confiabilidade, observabilidade e
operação — sem novas funcionalidades de usuário, sem alteração de
Orchestrator, Event Bus, Agents, Providers, OAuth ou APIs públicas. Toda
alteração nesta sprint é: (a) observabilidade nova e aditiva
(Correlation ID, OpenTelemetry), (b) um fix de config/CSS mínimo e
justificado por um achado real de auditoria, ou (c) um bug real
encontrado por teste de verdade (não hipotético) e corrigido com o
mínimo de código necessário, com teste de regressão.

Nenhuma regra de negócio, comportamento funcional existente, ou API
pública foi alterada. Todos os 13 checklists da sprint foram executados;
os itens que não podiam ser validados de ponta a ponta neste sandbox
(Google OAuth ao vivo, `docker compose up` real) estão documentados como
tal, não fabricados como "validados".

## Arquivos alterados

### Backend

| Arquivo | O que mudou |
|---|---|
| `backend/observability/request_context.py` | **Novo.** `RequestIDMiddleware` + `get_request_id()` (Correlation ID) |
| `backend/observability/tracing.py` | **Novo.** `setup_tracing()` — OpenTelemetry opcional, desligado por padrão |
| `backend/observability/__init__.py` | Exporta os dois novos símbolos |
| `backend/main.py` | Registra `RequestIDMiddleware` + chama `setup_tracing()` |
| `backend/utils/config.py` | + `otel_enabled`, `otel_exporter_otlp_endpoint` |
| `backend/utils/logging.py` | + `RequestIDFilter`; `request_id` em todo log JSON/texto |
| `backend/requirements.txt` | + 6 pacotes `opentelemetry-*` (opcionais) |
| `backend/memory/service.py` | **Bug fix real**: `client.search()` (removido do `qdrant-client` 1.18) → `client.query_points()` |
| `backend/tests/test_request_id.py` | **Novo.** 12 testes |
| `backend/tests/test_tracing.py` | **Novo.** 3 testes |
| `backend/tests/test_memory_service_search.py` | **Novo.** 3 testes de regressão para o bug do Qdrant |

### Frontend

| Arquivo | O que mudou |
|---|---|
| `frontend/hooks/useApi.ts` | **Bug fix real**: 401 só redireciona para `/login` se a requisição carregava um token (não mais em tentativas de login falhas) |
| `frontend/styles/globals.css` | Contraste do link ativo da sidebar (4.41→5.52:1); media query de responsividade mobile (sidebar vira barra horizontal <860px) |
| `frontend/styles/admin.css` | Contraste de `--admin-primary` (4.17→4.82:1) e `--admin-destructive` (3.8→4.92:1) |
| `frontend/components/admin/AdminShell.tsx` | `tabIndex={0}` na região rolável principal (achado de acessibilidade `scrollable-region-focusable`) |
| `frontend/app/favicon.ico` | **Novo.** Elimina 404 em toda carga de página |
| `frontend/next.config.mjs` | `@next/bundle-analyzer` atrás de `ANALYZE=true` (sem efeito em build normal) |
| `frontend/package.json` | + `@playwright/test`, `@axe-core/playwright`, `@next/bundle-analyzer`; scripts `analyze`, `e2e` |
| `frontend/playwright.config.ts` | **Novo.** Config Playwright (projeto autenticado + não-autenticado) |
| `frontend/e2e/*.spec.ts` | **Novo.** 23 testes E2E: login, responsividade, acessibilidade, teclado, loading/error, performance |
| `frontend/e2e/global-setup.ts` | **Novo.** Login real via UI, salva `storageState` |
| `frontend/tests/useApi.test.ts` | **Novo.** 2 testes de regressão para o bug do redirect 401 |

### Documentação

`PRODUCTION_READINESS.md`, `SECURITY_AUDIT.md`, `PERFORMANCE_REPORT.md`,
`OBSERVABILITY_GUIDE.md`, `OPERATIONS_RUNBOOK.md`, `DISASTER_RECOVERY.md`
(todos novos) + `.gitignore` (+ artefatos do Playwright).

## Bugs encontrados

1. **`MemoryService.search()` chamava um método removido do
   `qdrant-client`.** `AsyncQdrantClient.search()` não existe mais na
   versão 1.18.0 (a que `qdrant-client>=1.12,<2` resolve hoje) —
   substituído por `query_points()`. Toda busca semântica de memória
   (`long_term_search`, `knowledge_search`, memória de contato) quebrava
   com `AttributeError` em produção. Encontrado validando o Memory
   Manager contra um Qdrant real (embutido), não um mock.
2. **Login com senha errada não mostrava erro** — `apiFetch` tratava
   qualquer 401 (inclusive o de uma tentativa de login anônima, sem
   token) como sessão expirada e forçava `window.location.href =
   "/login"`, atropelando o `setError()` do formulário antes de
   renderizar. Encontrado por um teste Playwright real.
3. **`favicon.ico` inexistente** — 404 em toda carga de página (achado
   pelo teste de performance/console-limpo).
4. **3 violações WCAG 2 AA de contraste de cor** (sidebar principal, nav
   do admin, badges "Offline") e **1 região rolável sem foco por
   teclado** — achadas por `@axe-core/playwright` contra páginas reais
   autenticadas.
5. **Overflow horizontal em mobile** em `/` e `/conversas` — sidebar fixa
   de 230px sem nenhuma media query.

## Bugs corrigidos

Todos os 5 acima, com o menor diff possível em cada caso, sem tocar
lógica de negócio, e cada um com teste de regressão novo (backend: 3
testes; frontend: 2 testes unitários + os próprios testes E2E que
originalmente pegaram os bugs de UI/CSS).

## Melhorias (aditivas, não alteram comportamento existente)

- Correlation ID (`X-Request-ID`) em toda requisição/resposta/log.
- Tracing distribuído opcional via OpenTelemetry (`OTEL_ENABLED=false` por
  padrão — zero overhead até ser ligado).
- Bundle analyzer sob demanda (`ANALYZE=true npm run build`).
- Suíte E2E real com Playwright (antes inexistente neste projeto).

## Resultados dos testes

| Suíte | Resultado |
|---|---|
| Pytest (backend) | **555 passed**, 0 failed |
| Coverage (backend) | **94%** (≥90% exigido) |
| Ruff | All checks passed |
| Vitest (frontend) | **108 passed** (25 arquivos) |
| TypeScript (`tsc --noEmit`) | 0 erros |
| ESLint | 0 erros/warnings |
| Next.js build (produção) | Sucesso, 27 rotas |
| Playwright (E2E) | **23 passed**, 0 failed |
| `alembic check` (migration drift) | Nenhuma operação pendente detectada |
| `docker compose config` | Válido (estrutura confirmada com `.env` de exemplo preenchido) |

Total de testes automatizados novos ou existentes passando nesta sprint:
**555 (backend) + 108 (frontend unit) + 23 (E2E) = 686**, acima do piso de
479 exigido pela Fase 13.

## Cobertura

94% no backend (`--cov=. --cov-report=term-missing`), acima do mínimo de
90% exigido. Os módulos abaixo de 90% são majoritariamente caminhos de
fallback de infraestrutura indisponível (Redis fora do ar, providers de
WhatsApp alternativos não usados em produção) — não lógica de negócio
sem cobertura.

## Performance

Ver `PERFORMANCE_REPORT.md`. Resumo: bundles dentro do esperado para um
dashboard interno (maior rota: `/admin`, 254 kB First Load JS), sem sinal
de N+1 ou necessidade de virtualização, todas as rotas testadas carregam
em <5s sem erros de console no dev server.

## Segurança

Ver `SECURITY_AUDIT.md`. Resumo: nenhuma vulnerabilidade de severidade
alta no código da aplicação. Dois gaps documentados e propositalmente não
corrigidos por exigirem trabalho fora do escopo mínimo desta sprint: CSP/HSTS
ausentes no Caddyfile, e CVEs em `next@14.2.21` que só se resolvem com um
upgrade major (breaking) do Next.js.

## Observabilidade

Ver `OBSERVABILITY_GUIDE.md`. Correlation ID, structured logging JSON com
`request_id`, tracing OpenTelemetry opcional, e confirmação de que as
métricas Prometheus por endpoint/agent/tool/provider já existiam e
cobrem o pedido da Fase 2 sem necessidade de métricas novas.

## Checklist final (critério de aceitação da sprint)

- [x] TypeScript
- [x] ESLint
- [x] Ruff
- [x] Pytest (555 passed)
- [x] Frontend Tests (108 passed)
- [x] Playwright (23 passed)
- [x] Docker Compose (config válido; `up` real bloqueado pela política de
      rede deste sandbox — mesma limitação já documentada na Sprint 4)
- [x] PostgreSQL (real, local, toda a suíte roda contra ele)
- [x] Qdrant (real, embutido — não mockado; foi assim que o bug #1 foi
      encontrado)
- [~] Google OAuth (validado por código; sem credenciais reais neste
      sandbox para round-trip ao vivo — ver `GOOGLE_PLATFORM_AUDIT.md`)
- [x] Coverage ≥ 90% (94%)

## Veredito

**APROVADO PARA PRODUÇÃO**, com duas ressalvas documentadas e não
bloqueantes a validar no próprio ambiente de produção/staging antes do
próximo deploy, ambas fora do alcance de um sandbox local:

1. `docker compose up -d --build` completo (a config já está validada
   estruturalmente; falta apenas o pull de imagens, bloqueado pela rede
   deste sandbox).
2. Round-trip completo de Google OAuth com credenciais reais.

Nenhuma dessas ressalvas é um defeito de código encontrado nesta
auditoria — são limitações do ambiente de validação, não da aplicação.
