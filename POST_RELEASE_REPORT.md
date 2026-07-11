# Post-Release Report — v1.2.0

Consolidação pós-release da v1.2.0. Tarefa exclusivamente de documentação
e planejamento — nenhum código de produção foi alterado (as duas únicas
mudanças fora de `*.md` são `docs/` correções de referência dentro de
arquivos de documentação).

## Resumo da release

**v1.2.0** (tag `v1.2.0`, commit `174569a`, 2026-07-11) — Dashboard
Administrativo (Sprint 4) + Production Hardening (Sprint 5):
observabilidade (Correlation ID, OpenTelemetry opcional), suíte E2E com
Playwright, dois bugs reais de produção corrigidos (busca semântica de
memória quebrada pelo `qdrant-client` 1.18+; erro de login não exibido na
UI), auditoria de segurança/performance. Ver `SPRINT5_REPORT.md` e
`DASHBOARD_REPORT.md` para os relatórios técnicos completos de cada
sprint.

## Arquivos criados

| Arquivo | Conteúdo |
|---|---|
| `VERSION_HISTORY.md` | Linha do tempo completa v1.0.0 → v1.2.0 |
| `ROADMAP_v2.md` | Planejamento v1.2.1 → v2.0.0 |
| `TECHNICAL_DEBT.md` | Débito técnico real, com fonte de cada item |
| `KNOWN_LIMITATIONS.md` | Limitações reais e verificadas |
| `CONTRIBUTING.md` | Padrões, como criar Agent/Provider/Tool, testes, migrations |
| `PROJECT_STATUS.md` | Resumo executivo com contagens reais |
| `POST_RELEASE_REPORT.md` | Este arquivo |

## Arquivos alterados

| Arquivo | O que mudou |
|---|---|
| `CHANGELOG.md` | Adicionadas as entradas faltantes v1.1.1, v1.1.2, v1.2.0 (só existia v1.0.0) |
| `README.md` | Contagem de testes desatualizada (540/106 → 555/108); adicionado Playwright ao fluxo de testes; adicionadas as linhas de Correlation ID/OpenTelemetry (Sprint 5) que faltavam na seção Observabilidade; adicionados os 6 novos documentos ao índice de Documentação |
| `docs/architecture.md` | Seção Observabilidade não mencionava Correlation ID nem OpenTelemetry (Sprint 5); corrigida referência a `create_event`/`create_calendar_event` |
| `docs/api.md` | Faltava toda a seção de endpoints `/api/admin/*` (12 rotas, Sprint 4) |
| `docs/TOOLS.md` | Nomes de tool errados no catálogo: `create_event`/`list_events` não existem — os nomes reais são `create_calendar_event`/`list_calendar_events` |
| `docs/CALENDAR.md` | Mesmo erro de nome de tool, em duas ocorrências |
| `docs/EMAIL.md` | Mesmo erro de nome de tool, em uma ocorrência |

## Resultado das validações

| Validação | Resultado |
|---|---|
| Links quebrados (51 arquivos `.md` verificados) | ✅ 0 encontrados |
| Imagens inexistentes | ✅ N/A — nenhuma imagem referenciada em nenhum `.md` do projeto |
| Referências a versões antigas | ✅ 7 encontradas e corrigidas (ver "Arquivos alterados") |
| TypeScript (`tsc --noEmit`) | ✅ 0 erros |
| ESLint | ✅ 0 erros/warnings |
| Ruff | ✅ All checks passed |
| Pytest | ✅ 555 passed |
| Frontend tests (Vitest) | ✅ 108 passed |
| Playwright (E2E) | ✅ 23 passed |
| Build de produção (Next.js) | ✅ sucesso, 27 rotas |
| `docker compose config` | ✅ válido (estrutura confirmada com `.env` de exemplo preenchido) |
| `git status` | ✅ limpo antes do commit; nada fora do escopo desta tarefa |

## Próximos passos

1. **Nenhuma sprint nova inicia a partir deste commit** — conforme
   instrução explícita desta tarefa.
2. Quando uma sprint futura for aberta, `ROADMAP_v2.md` já tem o escopo
   candidato de v1.2.1 (correções críticas apenas) até v2.0.0 (autonomia
   cognitiva), em ordem de dependência.
3. `KNOWN_LIMITATIONS.md` e `TECHNICAL_DEBT.md` são os pontos de partida
   para priorizar o que entra em cada versão futura.
4. Dois itens seguem pendentes de validação em um ambiente fora de
   sandbox, não bloqueantes para esta consolidação: `docker compose up`
   completo e um round-trip real de Google OAuth (ambos já documentados
   como limitação de ambiente, não de código, desde a v1.2.0).

## Veredito

Todas as validações passaram. Commit realizado.
