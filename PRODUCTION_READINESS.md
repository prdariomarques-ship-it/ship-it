# Production Readiness — Sprint 5

Consolidated production-hardening review of Dario OS. This sprint added no
user-facing functionality — every change here is observability, security,
performance, or reliability work, or a bug fix surfaced by real testing.
See `SPRINT5_REPORT.md` for the full executive summary and verdict.

## Scope discipline

Per the sprint's explicit restrictions, the following were **not** touched:
Orchestrator, Event Bus, Agents, Providers' business logic, OAuth flows,
public API contracts, or existing functional behavior. Every change below
is either additive (observability), a config/CSS-level fix, or a genuine
bug fix backed by a failing test that now passes.

## Checklist

| Área | Status | Evidência |
|---|---|---|
| TypeScript | ✅ | `npx tsc --noEmit` — 0 erros |
| ESLint | ✅ | `npx eslint . --ext .ts,.tsx` — 0 erros/warnings |
| Ruff | ✅ | `ruff check .` — All checks passed |
| Pytest | ✅ | 555 passed, 0 failed |
| Coverage (backend) | ✅ | 94% (≥90% exigido) |
| Frontend unit tests (Vitest) | ✅ | 108 passed (25 arquivos) |
| Playwright (E2E) | ✅ | 23 passed (login, responsividade, acessibilidade, teclado, loading/error, performance) |
| Next.js production build | ✅ | `npm run build` — compila sem erros, 27 rotas estáticas |
| Docker Compose config | ✅ | `docker compose config` válido (up/down real bloqueado pelo sandbox — ver `OPERATIONS_RUNBOOK.md`) |
| Migrations (Alembic) | ✅ | `alembic check` — no drift; upgrade head limpo em banco novo |
| PostgreSQL | ✅ | Real, local, todas as 555 suítes rodam contra Postgres real |
| Qdrant | ✅ | Real (embedded in-memory `qdrant-client`), não mockado — ver `docs/MEMORY.md` e achados abaixo |
| Google OAuth | ⚠️ | Validado por código/testes; sem credenciais reais neste sandbox para round-trip ao vivo — ver `GOOGLE_PLATFORM_AUDIT.md` |
| Mypy | N/A | Não configurado no projeto (nenhum `mypy.ini`/seção `[tool.mypy]`); fora do escopo mínimo desta sprint introduzir uma nova ferramenta de tipagem |

## Bugs reais encontrados e corrigidos nesta sprint

1. **`MemoryService.search()` chamava um método removido do `qdrant-client`.**
   `AsyncQdrantClient.search()` foi removido no `qdrant-client` 1.18+ (o
   range fixado `>=1.12,<2` resolve para 1.18.0). Toda busca semântica de
   memória (`long_term_search`, `knowledge_search`, contact memory) quebrava
   com `AttributeError` em produção. Corrigido para `query_points()`.
   `backend/memory/service.py`. 3 testes de regressão novos.

2. **Login com credenciais erradas redirecionava para `/login` em vez de
   mostrar o erro inline.** `apiFetch` tratava qualquer 401 — inclusive o
   401 de uma tentativa de login sem token — como "sessão expirada" e
   forçava `window.location.href = "/login"`, atropelando o estado de erro
   do formulário antes de renderizar. Corrigido para só disparar esse
   fluxo quando a requisição carregava um token de acesso.
   `frontend/hooks/useApi.ts`. Encontrado por um teste Playwright real,
   confirmado por testes unitários novos.

3. **`favicon.ico` ausente** — 404 em toda carga de página, ruído real de
   console capturado pelos testes de performance. `frontend/app/favicon.ico`.

4. **3 violações WCAG 2 AA de contraste de cor** (sidebar principal, nav do
   admin, badges "Offline" do admin) e **1 região rolável sem foco por
   teclado** (`<main>` do admin) — encontradas por `@axe-core/playwright`
   contra páginas reais, corrigidas ajustando variáveis de cor existentes
   (sem trocar paleta) e adicionando `tabIndex={0}`.

5. **Overflow horizontal em mobile** (`/`, `/conversas`) — a sidebar fixa de
   230px não tinha nenhuma media query; em 375px de largura o
   `scrollWidth` excedia o `clientWidth`. Corrigido com uma media query que
   transforma a sidebar em barra horizontal rolável abaixo de 860px —
   nenhum elemento novo de UI, apenas o layout existente se adaptando.

## Achados documentados, não corrigidos (fora do escopo mínimo)

- **Dark mode**: não existe no produto (nenhum `ThemeProvider`, nenhuma
  variante `dark:` usada, nenhum toggle). Implementá-lo seria uma nova
  funcionalidade de usuário — explicitamente vedado por esta sprint.
- **CVEs em `next@14.2.21`/`postcss`** (`npm audit`): corrigir exige subir
  para `next@16.x`, uma mudança breaking fora do escopo de "alteração
  mínima e justificada". Ver `SECURITY_AUDIT.md`.
- **CSP / HSTS ausentes no Caddyfile**: gap real, mas adicionar CSP sem
  testar contra HTTPS real neste sandbox arrisca quebrar assets em
  produção sem forma de validar aqui. Ver `SECURITY_AUDIT.md`.
- **Google OAuth / Docker `up`**: não executáveis de ponta a ponta neste
  sandbox (sem credenciais reais / pull de imagem Docker bloqueado pela
  rede do ambiente). Validados estruturalmente; ver seções específicas em
  `GOOGLE_PLATFORM_AUDIT.md` e `OPERATIONS_RUNBOOK.md`.

## Veredito

Ver `SPRINT5_REPORT.md`.
