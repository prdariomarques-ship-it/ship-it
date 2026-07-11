# Performance Report — Sprint 5

## Frontend

### Bundle size (`npm run build`, Next.js 14.2.21 production build)

| Rota | Size | First Load JS |
|---|---|---|
| `/` | 2.23 kB | 89.4 kB |
| `/admin` | 42.5 kB | 254 kB |
| `/admin/metrics` | 1.99 kB | 213 kB |
| `/admin/system` | 1.72 kB | 213 kB |
| `/admin/executions` | 18.9 kB | 140 kB |
| demais rotas do app principal | 2.1–2.4 kB | ~89 kB |
| demais rotas do admin | 3.7–5.1 kB | ~111–124 kB |
| Shared JS (todas as rotas) | — | 87.2 kB |

`/admin` é a rota mais pesada (254 kB) por concentrar Recharts +
React Query + todos os componentes do dashboard administrativo na página
inicial do admin. Nenhuma rota excede o que é razoável para um dashboard
interno autenticado — não há sinal de bundle bloat que justifique
code-splitting adicional agora. `@next/bundle-analyzer` foi instalado e
cabeado atrás de `ANALYZE=true npm run build` (`frontend/next.config.mjs`,
`frontend/package.json`) para investigação futura sob demanda, sem efeito
em builds normais.

### Code splitting

Next.js App Router já faz code-splitting por rota automaticamente (visível
na tabela acima — cada página carrega apenas seu próprio JS + o shared
chunk). Nenhuma rota compartilha componentes pesados desnecessariamente.

### Virtualização

Nenhuma tabela/lista no dashboard atual opera em uma escala (milhares de
linhas renderizadas de uma vez) que justifique virtualização — decisão
deliberada de não adicionar essa complexidade sem evidência de um problema
real, conforme "não fazer refatorações desnecessárias".

### Client-side runtime (Playwright, `e2e/performance.spec.ts`)

Carregamento de `/`, `/conversas` e `/admin` medido de ponta a ponta
(`page.goto` até `networkidle`) contra o dev server real: todas as três
rotas carregam em menos de 5s (limite do teste), sem erros de console —
depois de corrigir o 404 de `favicon.ico` que aparecia em toda carga de
página (ver `PRODUCTION_READINESS.md`).

## Backend

### N+1 queries

Revisão dos repositórios (`repositories/*.py`) e dos routers que listam
recursos relacionados (contatos, mensagens, execuções de agente) — uso
consistente de `selectinload`/joins explícitos onde há relacionamento
1:N acessado em listagem; nenhum padrão de N+1 novo introduzido ou
encontrado nesta auditoria.

### Cache

`services/cache.py` (Redis, com fallback seguro) já existente e em uso
para endpoints de leitura pesada. Sem alteração — apenas confirmado que
segue coberto por teste (82% de cobertura no arquivo, gaps são os
caminhos de fallback do Redis indisponível).

### Compressão

`encode gzip` já ativo no Caddy (camada de borda) — confirmado, sem
alteração.

### Qdrant (busca vetorial)

Validado com um motor Qdrant real (embutido, `qdrant-client(":memory:")`)
contra o `MemoryService` real, sem mocks: `store`, `search`
(`long_term_search`/`knowledge_search`), duplicata de conteúdo,
`forget` (remoção Postgres + Qdrant) e um fluxo de reindex simulado
(padrão do indexador do Google Drive) — todas as operações completam sem
degradação perceptível no volume de teste. Ver achado de bug real nesta
mesma área em `PRODUCTION_READINESS.md`.

## Não medido neste sandbox

- **Lighthouse**: exige um navegador completo com DevTools Protocol e,
  idealmente, uma build de produção servida via HTTP real — não executado
  como ferramenta separada nesta sessão; as métricas de carregamento
  client-side acima (via Playwright, no dev server) servem como proxy
  parcial. Recomendação: rodar `next start` + Lighthouse CI em um pipeline
  de CI real antes do próximo release.
- **Carga/stress real de produção** (milhares de usuários simultâneos):
  fora do escopo de uma sessão de sandbox local.
