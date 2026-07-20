# Roadmap — v1.4

Preparado no fechamento formal da v1.3.1 (2026-07-19). Prioridades vindas do
audit final de produção (`RELEASE_1_3_1_POSTMORTEM.md`) e do backlog de
`TECHNICAL_DEBT.md`.

## Must Have

1. ~~Corrigir `docker-compose.yml`: `POSTGRES_PASSWORD` sem fallback fraco.~~
   **Concluído** — `${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}`
   aplicado tanto no `DATABASE_URL` do backend quanto no próprio serviço
   `postgres`. Ver commit `8dfb6db`.
2. ~~Corrigir roteamento do Caddy pra `/health/ready`.~~ **Concluído** —
   `handle /health/ready { reverse_proxy backend:8000 }` adicionado ao
   Caddyfile. Ver commit `cbdd068`.
3. ~~Cobertura de teste para `chat_router`.~~ **Concluído** — junto com o
   item 4 (Should Have) na mesma sessão. Ver commit `fa3585e`.

## Should Have

4. ~~Cobertura de teste para `workflows_router`~~ **Concluído** — junto com
   o item 3 (Must Have) na mesma sessão de fechamento dos itens de
   cobertura. `workflows/router.py` e `workflows/service.py`: 100% de
   cobertura de statement, 13 testes. Ver commit `fa3585e`.
5. ~~Timeout por chamada individual a provider LLM~~ **Concluído** —
   `llm_request_timeout_seconds` aplicado a openai/anthropic/gemini
   (glm/ollama herdam via `OpenAIProvider`). Ver commit `cc13b9f`.
6. ~~Decidir o destino de `backend/business/models.py`~~ **Concluído** —
   removido (pacote inteiro: `models.py`, `schemas.py`, `__init__.py`).
   Nenhum plano existia pra construir a feature CRM; conectá-la seria
   escopo novo, fora da regra deste ciclo de limpeza. As migrations
   (`MIG-001`–`MIG-005`) e as tabelas num banco real não foram tocadas —
   já estavam desconectadas do `Base.metadata`/autogenerate antes disso
   (`alembic/env.py` só importa `models`, nunca importou `business`), sem
   risco adicional em deixá-las como estão. Ver `TECHNICAL_DEBT.md`.
7. **CSP no Caddyfile.** HSTS já presente; falta `Content-Security-Policy`.
   Precisa de um domínio real com HTTPS pra testar com segurança — não dá
   pra validar contra `DOMAIN=localhost`. Esforço: 2–4h incluindo teste.
   **Ainda pendente** — único item Should Have não concluído neste ciclo.
8. ~~Upgrade do Next.js (14→16)~~ **Concluído e em produção.** Feito em
   branch isolada (`chore/nextjs-16-upgrade`), PR #4, merge `1ea265b`,
   deploy em produção validado (healthcheck, smoke test funcional, zero
   regressão de performance/memória). Ver `RELEASE_REPORT_NEXTJS16.md`
   para o relatório completo da migração.

## Nice to Have

9. ~~Métrica Prometheus dedicada pra "job atingiu o timeout global de
   execução"~~ **Concluído** — `darioos_job_timeouts_total`, incrementado
   exatamente onde o timeout já era distinguido de qualquer outra falha
   (`jobs/worker.py`). Testes confirmam que não incrementa numa falha
   comum, só num timeout de verdade.
10. ~~Completar healthcheck do Docker~~ **Concluído** — `backend` (achado
    fora da lista original, também não tinha), `frontend`, `openwa`,
    `redis`, `qdrant`, `caddy`, `n8n`, `jaeger`. Cada comando verificado
    contra o container real antes de escrever (qdrant não tem wget/curl,
    frontend não faz bind em `localhost`). Aplicado ao vivo: um incidente
    real foi encontrado e corrigido no processo (lock stale do Chromium no
    `openwa` após a recriação do container) — ver
    `RELEASE_1_3_1_POSTMORTEM.md` ou o commit pra detalhes.
11. Fluxo de "esqueci minha senha" (hoje só existe troca autenticada).
12. Granularidade de RBAC além do binário ADMIN/USER — avaliar se
    `contacts`/`church`/`store` deveriam ser escopados por usuário/equipe.
13. Resolver GitHub Issue #2 (`getConnectionState()` `TypeError`) — não
    bloqueia (fallback via `isConnected()` funciona), causa raiz já
    identificada.
14. Validar Google OAuth ponta a ponta contra credenciais reais — depende
    de ação externa (setup no Google Cloud Console), não é só trabalho de
    engenharia.
15. Testar o restore do Postgres ponta a ponta contra dado real (hoje só
    automatizado, nunca executado de fato pelo risco destrutivo de provar
    isso contra produção).
16. Circuit breaker / bulkhead para os providers externos (Google, LLM,
    WhatsApp).

## Dependências entre itens

- Item 7 (CSP) depende de ter um domínio real com HTTPS — não pode ser
  feito com segurança contra `DOMAIN=localhost`. Único item restante desta
  lista, e único bloqueado por fator externo (não é falta de trabalho).

## Paralelizável

Todos os itens Must Have e quase todos os Should/Nice to Have deste roadmap
foram concluídos neste ciclo (v1.4). Resta apenas o item 7 (CSP), bloqueado
por fator externo, e os itens 11–16 (Nice to Have, não iniciados — ver
seção acima para status individual de cada um).

## Status ao final do ciclo v1.4

- **Must Have:** 3/3 concluídos.
- **Should Have:** 4/5 concluídos (falta apenas CSP, item 7, bloqueado por
  fator externo).
- **Nice to Have:** 2/8 concluídos (itens 9 e 10); itens 11–16 seguem no
  backlog, nenhum é bloqueante para o próximo ciclo (v1.5).
