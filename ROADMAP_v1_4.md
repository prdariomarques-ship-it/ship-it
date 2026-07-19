# Roadmap — v1.4

Preparado no fechamento formal da v1.3.1 (2026-07-19). Prioridades vindas do
audit final de produção (`RELEASE_1_3_1_POSTMORTEM.md`) e do backlog de
`TECHNICAL_DEBT.md`.

## Must Have

1. **Corrigir `docker-compose.yml`: `POSTGRES_PASSWORD` sem fallback fraco.**
   Mesmo padrão de bug que acabou de ser corrigido no Grafana
   (`GF_SECURITY_ADMIN_PASSWORD:?...`), ainda não aplicado ao Postgres —
   trocar `${POSTGRES_PASSWORD:-dario}` por
   `${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}`. Achado nesta
   mesma sessão, P1. Esforço: ~15min.
2. **Corrigir roteamento do Caddy pra `/health/ready`.** Ver
   `docs/issues/caddy-health-ready-routing.md` — problema, causa raiz e
   correção sugerida já documentados. P1. Esforço: ~30min + teste de
   regressão.
3. **Cobertura de teste para `chat_router`.** Zero teste hoje num endpoint
   central (IA conversacional), montado e acessível. P1. Esforço: 3–5h.

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
8. **Upgrade do Next.js (14→16)** pra resolver as CVEs remanescentes (`npm
   audit`: 1 moderada + 4 altas). Breaking change — merece branch isolada e
   suíte de regressão completa antes de mesclar, não deve ser feito junto
   com outra coisa. Esforço: 1–2 dias.

## Nice to Have

9. Métrica Prometheus dedicada pra "job atingiu o timeout global de
   execução" (hoje só visível via grep no log persistido).
10. Completar healthcheck do Docker nos serviços que ainda não têm
    (`frontend`, `openwa`, `redis`, `qdrant`, `caddy`, `n8n`, `jaeger`).
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

- Item 2 (Caddy) é independente de tudo — pode ser feito a qualquer momento.
- Item 1 (Postgres fallback) é independente — só editar o compose file,
  sem precisar rotacionar credencial de novo (o valor real já está correto
  em `.env`).
- Itens 3 e 4 (cobertura de teste) são independentes entre si e do resto.
- Item 5 (timeout por provider) continua tematicamente o timeout global já
  implementado, mas não depende dele tecnicamente.
- Item 7 (CSP) depende de ter um domínio real com HTTPS — não pode ser
  feito com segurança contra `DOMAIN=localhost`.
- Item 8 (Next.js) deve ficar isolado numa branch própria — não combinar
  com nenhum outro item desta lista.

## Paralelizável

Itens 1, 2, 3, 4, 6 e 9–16 podem todos rodar em paralelo entre si — nenhum
tem dependência real nos outros. Item 8 (Next.js) deve ficar isolado por
causa do risco de regressão, não por dependência técnica.
