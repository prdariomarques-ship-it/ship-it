# Dario OS v1.0 — Production Approval Report

**Papel**: Comitê de Release (Principal Engineer) — auditoria final antes do congelamento de arquitetura.
**Data**: 2026-07-10 (auditoria original) — atualizado em 2026-07-10 após a correção dos bloqueadores PROD-004 e PROD-005.
**Branch auditada**: `claude/dario-os-platform-gcg6i2` (auditoria original @ `6ba7e95`; correções aplicadas em commit posterior — ver `PRODUCTION_BLOCKERS_RESOLVED.md`).
**Escopo**: auditoria e validação; a correção dos dois bloqueadores foi feita como tarefa isolada e mínima (sem funcionalidade nova, sem mudança de arquitetura, sem módulo novo) — ver `PRODUCTION_BLOCKERS_RESOLVED.md` para o detalhe exato do que mudou.

---

## 1. Resumo Executivo

O Dario OS chega a este gate com uma base técnica sólida: 246 testes automatizados passando, cobertura de 92%, arquitetura consolidada em torno de Agent Registry, Tool Registry, Event Bus, AI Orchestrator e Memory Manager, um Cognitive Pipeline funcional que classifica intenção/prioridade, planeja e valida antes de responder, e uma camada de Providers de WhatsApp totalmente desacoplada da tecnologia específica do gateway. A engenharia de confiabilidade (fila de jobs durável, retry exponencial, degradação graciosa de Redis/Qdrant/WhatsApp, recuperação de jobs travados, idempotência de mensagens) está madura e comprovada por teste, não apenas documentada.

A auditoria original encontrou **dois bloqueadores de segurança reais e concretos** na camada de entrada/execução (webhook do WhatsApp e escopo das ferramentas de contato/envio) que existiam antes desta release mas nunca haviam sido avaliados sob uma lente adversarial rigorosa. Ambos foram corrigidos em uma etapa dedicada e mínima, com testes específicos comprovando o fechamento de cada um (`PRODUCTION_BLOCKERS_RESOLVED.md`), sem introduzir nenhuma funcionalidade nova ou mudança arquitetural. Com as duas correções verificadas — suíte completa passando, isolamento técnico confirmado por teste, boot em produção agora recusado sem `WEBHOOK_SECRET` forte —, **este release está APROVADO para produção**.

## 2. Arquitetura Final

```
Rotas (FastAPI) ──→ AI Orchestrator ──→ Agent Registry ──→ BaseAgent
  (chat, agents,        │                (auto-discovery)   (planner + executor + tools)
   webhooks)            │
                        ▼
                   Cognitive Pipeline (intent, priority, planning, validation, learning)
                        │
                        ▼
                   Event Bus (pub/sub)  ◄── publicado por webhooks, jobs, orquestrador
                        │
                        ▼
        Serviços (casos de uso) ──→ Repositórios ──→ Banco (Postgres)
                        │
                        └──→ Providers (LLM Strategy: 5 vendors / WhatsApp Strategy: 4 gateways)
                        └──→ Memory Manager (curto prazo / longo prazo / conhecimento / preferências / resumo)
                        └──→ Fila de jobs (Postgres, retry exponencial, claim atômico)
```

Camadas: Apresentação (`api/`, `*/router.py`, `webhooks/`) → Coordenação cognitiva (`orchestrator/`, `agents/registry.py`, `agents/tools/registry.py`) → Aplicação (services) → Domínio (`models/`) → Acesso a dados (`repositories/`) → Infraestrutura (`providers/`, `database/`, `events/`, `jobs/worker`). Nenhuma camada nova foi adicionada nesta etapa; a arquitetura documentada em `docs/architecture.md` corresponde ao código auditado (verificado por leitura direta do código-fonte, não apenas da documentação).

Diagramas completos (Cognitive Pipeline, fluxo do Planner, fluxo de memória, fluxo de ferramentas, fluxo de agentes): `docs/architecture.md`.

## 3. Métricas

| Métrica | Valor |
| --- | --- |
| Linhas de código (backend, aprox.) | ~5.660 (medidas via coverage) |
| Testes automatizados | 246 (231 da auditoria original + 15 dos bloqueadores corrigidos) |
| Cobertura de linha total | 92% |
| Cobertura dos módulos do Cognitive Pipeline | 92–100% |
| Lint (`ruff check .`) | limpo, zero violações |
| Migrações Alembic | 3, sem drift de schema (`alembic check` limpo) |
| Métricas Prometheus expostas | 16 |
| Agentes registrados | 5 |
| Ferramentas registradas | ~20 |
| Providers de LLM | 5 (openai, anthropic, glm, gemini, ollama) |
| Providers de WhatsApp | 4 (openwa, baileys, evolution, official) |
| Vulnerabilidades de dependência (frontend, `npm audit`) | 2 (1 crítica, 1 moderada — `next@14.2.21`; sem vetor de exploração identificado nesta aplicação, ver §11) |

## 4. Cobertura de Testes

Suíte completa executada após as correções: **246 passed, 0 failed, 3 warnings** (`pytest -q`, ambiente limpo) — 15 testes novos (`test_audit_fixes.py` para PROD-004, `test_tool_isolation.py` para PROD-005), nenhum teste pré-existente quebrado. Cobertura por área:

| Área | Cobertura |
| --- | --- |
| `orchestrator/` (AI Orchestrator + Cognitive Pipeline) | 92% |
| `agents/` (registry, executor, planner, tools) | 87–100% por arquivo |
| `providers/whatsapp/` | 76–96% por provider |
| `providers/llm/` | 81–100% por provider |
| `webhooks/router.py` | 50% de linha (nota de transparência: comportamento coberto por ~20 testes de integração diretos — ver `docs/fase4.1-relatorio.md` para a investigação da métrica de cobertura) |
| `repositories/`, `models/` | 96–100% |

Categorias de teste confirmadas presentes e passando: unitários (engines, planner, validator, tools), integração (webhook→job→pipeline→resposta), regressão (auditoria Fase 2, compatibilidade de Providers), simulação de falha (provider LLM levantando exceção, Qdrant indisponível, ferramenta com erro, job esgotando tentativas), concorrência (claim atômico de jobs, corrida de deduplicação de mensagem).

**Não executado nesta auditoria** (limitação do ambiente sandbox, não do produto): build real das imagens Docker e `docker compose up` completo — o daemon Docker deste ambiente de auditoria não tem acesso ao registry do Docker Hub (bloqueio de política de rede do sandbox, confirmado por erro 403 do CloudFront, não um erro do projeto). Validado como substituto: revisão estática dos Dockerfiles, `docker compose config` (interpolação de variáveis, sintaxe) com resultado válido. **Recomendação**: rodar `docker compose build && docker compose up` uma vez em ambiente com acesso ao registry antes do deploy real — o pipeline de CI atual (`.github/workflows/ci.yml`) também não constrói as imagens Docker, apenas lint+testes+migrações do backend e build do frontend.

## 5. Critérios de Segurança

**Verificado e aprovado**:
- Hashing de senha PBKDF2-HMAC-SHA256 (390k iterações), salt aleatório por usuário, comparação `hmac.compare_digest`, timing equalizado para e-mail inexistente (`_DUMMY_HASH`).
- JWT HS256 com expiração curta; refresh token opaco, armazenado como hash SHA-256, rotativo, reuso de token revogado rejeitado.
- Boot em produção recusado com `JWT_SECRET` ausente/fraco/padrão **e agora também com `WEBHOOK_SECRET` ausente/fraco** (`main.py::_validate_production_settings` — ver PROD-004 abaixo).
- RBAC (`require_admin`) genuinamente aplicado em `/api/jobs` e `/api/logs` (confirmado no código, não apenas na documentação).
- CORS com allow-list explícita de origem (não `*`), apesar de `allow_credentials=True`.
- Rate limiting por IP genuinamente conectado ao middleware HTTP global, com namespace separado reaproveitado para o freio de loop/flood do auto-reply do WhatsApp.
- Nenhuma SQL interpolada por string; todo acesso a dados via ORM parametrizado.
- Nenhum `eval`/`exec`/`subprocess`/`os.system` sobre entrada de usuário.
- Segredos não vazam em log (checado especificamente nos caminhos de auth e webhook); `.env` corretamente ignorado pelo git.
- Deduplicação de webhook (idempotência por `external_id` + constraint única no banco) resiliente a corrida entre requisições concorrentes.
- Frontend sem `dangerouslySetInnerHTML` e sem segredo embutido no bundle além da URL pública da API.
- **Isolamento técnico de contato nas ferramentas de envio/consulta** (ver PROD-005 abaixo) — decisão de autorização inteiramente em código, não em prompt.

**PROD-004 — CORRIGIDO. Webhook do WhatsApp agora exige `WEBHOOK_SECRET` forte em produção.**
`backend/main.py::_validate_production_settings` recusa o boot em produção se `WEBHOOK_SECRET` estiver ausente ou tiver menos de 32 caracteres — mesmo padrão já aplicado a `JWT_SECRET`. `docker/docker-compose.yml` passou a exigir a variável (`${WEBHOOK_SECRET:?...}`, antes `${WEBHOOK_SECRET:-}`), e `scripts/setup.sh` passa a gerá-la automaticamente junto com `JWT_SECRET`. Coberto por 5 testes dedicados (`tests/test_audit_fixes.py`) cobrindo dev, prod, secret ausente, inválido e válido, mais 1 teste de não-regressão garantindo que a checagem de `JWT_SECRET` continua funcionando de forma independente. Validado operacionalmente: `docker compose config` confirmado recusando subir sem a variável. Detalhes completos: `PRODUCTION_BLOCKERS_RESOLVED.md`.

**PROD-005 — CORRIGIDO. Ferramentas de contato/envio agora têm isolamento técnico, não dependem de prompt.**
`ToolContext` (`backend/agents/tools/base.py`) ganhou o campo `contact_id`, preenchido pela aplicação (`BaseAgent.run`) a partir do estado da conversa — nunca pelo LLM. `_send_whatsapp` (`backend/agents/tools/communication.py`) agora só permite enviar para o telefone do contato da conversa atual quando há um contato associado, ou para um contato já conhecido pelo backend quando não há (nunca um número inventado pelo modelo). `_find_contact` só resolve para o contato da conversa atual quando há um contato associado; sem conversa associada, o comportamento de busca aberta (uso administrativo) é preservado. Coberto por 10 testes dedicados (`tests/test_tool_isolation.py`) simulando tentativas de acesso indevido (enviar/consultar outro contato, tentar burlar via formatação de telefone, número desconhecido sem escopo) — todas as tentativas negadas, nenhum job de envio enfileirado nas tentativas bloqueadas. Detalhes completos: `PRODUCTION_BLOCKERS_RESOLVED.md`.

**Riscos documentados, não classificados como bloqueadores** (ver §11): auto-registro aberto em `/api/auth/register` (afeta só o dashboard, não o canal de WhatsApp); ausência de detecção de reuso de refresh token roubado; tokens de acesso em `localStorage` no frontend (sem vetor de XSS identificado hoje); senha padrão do Postgres fraca (mitigado por não ser exposta externamente); `next@14.2.21` com CVEs conhecidas (sem vetor de exploração identificado nesta aplicação, sem `middleware.ts`).

## 6. Critérios de Performance

- Hashing de senha roda fora do event loop (thread pool) — não bloqueia requisições concorrentes.
- Embedding de mensagens roda fora do hot path da requisição (job assíncrono), não atrasa a resposta do webhook.
- Timeout de execução de agente (`AGENT_RUN_TIMEOUT_SECONDS`, padrão 60s) limita qualquer chamada LLM/loop de ferramentas travado.
- Cognitive Pipeline: até 3 chamadas LLM adicionais por mensagem (intenção, prioridade, planejamento) antes da execução do agente — custo/latência real e documentado (`docs/fase4.2-relatorio.md` §8), aceitável no volume atual, candidato a otimização (combinar as três decisões) caso o volume cresça.
- Contexto de memória carregado sob demanda: buscas semânticas (Qdrant) só ocorrem quando a intenção/prioridade justificam, evitando latência desnecessária em mensagens simples (saudação, conversa casual).
- Rate limiting (120 req/60s por IP, configurável) protege contra abuso de força bruta na API HTTP.

Nenhum teste de carga formal (k6, locust) foi executado nesta auditoria — não fazia parte do escopo solicitado, e não há infraestrutura de teste de carga no repositório atual. Isso é uma lacuna de validação, não uma falha confirmada.

## 7. Critérios de Escalabilidade

- Fila de jobs Postgres-backed com claim atômico (`SELECT ... FOR UPDATE SKIP LOCKED`) — múltiplos workers podem rodar em paralelo sem processar o mesmo job duas vezes; hoje roda embutido no processo da API por padrão, mas a extração para um container de worker dedicado não exige mudança de código de enfileiramento.
- Cache e rate limiter usam Redis com fallback local em memória — o fallback funciona para uma única instância, mas **não é compartilhado entre réplicas**: rodar múltiplas instâncias do backend sem Redis disponível faria cada réplica ter seu próprio rate limit/cache, divergindo do comportamento pretendido. Com Redis disponível (o caso normal), isso não é um problema.
- Qdrant e Postgres são serviços externos ao processo da API, escaláveis independentemente.
- O Cognitive Pipeline é stateless por execução (todo estado vem do banco/memória a cada chamada) — não há estado em memória do processo que impeça múltiplas réplicas do backend.

## 8. Checklist de Deploy

| Item | Status |
| --- | --- |
| Build do backend (`pip install -r requirements.txt`) | ✅ verificado (dependências resolvidas, testes rodam) |
| Lint (`ruff check .`) | ✅ limpo |
| Testes (`pytest -q`) | ✅ 246 passed |
| Migrações (`alembic upgrade head` / `downgrade base` / roundtrip) | ✅ verificado nesta auditoria |
| Drift de schema (`alembic check`) | ✅ nenhuma operação pendente detectada |
| Build do frontend (`npm run build`) | ⚠️ não executado nesta auditoria (sem acesso de rede ao registry npm completo no ambiente de sandbox para todas as dependências transitivas do Next.js); `next build` já roda no CI a cada PR |
| `docker compose config` (sintaxe/interpolação) | ✅ válido, com `JWT_SECRET` **e `WEBHOOK_SECRET`** obrigatórios confirmados (`:?`) |
| `docker build` das imagens | ❌ não executado (registry do Docker Hub bloqueado neste sandbox — ver §4) |
| `docker compose up` (inicialização completa) | ❌ não executado (mesma limitação) |
| Health checks (`/health`, `/health/ready`) | ✅ lógica verificada por leitura direta do código e por teste (`test_observability.py`) — Postgres obrigatório, Redis/Qdrant/WhatsApp degradam sem derrubar |
| `WEBHOOK_SECRET` obrigatório em produção | ✅ **implementado (PROD-004)** — boot recusado sem um valor forte; `scripts/setup.sh` gera automaticamente |
| Variáveis de ambiente documentadas em `.env.example` | ✅ presentes (exceto `LLM_FALLBACK_PROVIDER`, opcional, default seguro) |
| CI (lint + testes + migrações + build frontend) | ✅ configurado e cobrindo o essencial; não constrói imagens Docker |

## 9. Checklist de Backup

| Item | Status |
| --- | --- |
| Script de backup (`scripts/backup.sh`) | ✅ existe, documentado no README como agendável via cron |
| Dados persistidos em volumes Docker nomeados (Postgres, Redis, Qdrant, n8n, OpenWA) | ✅ configurado em `docker-compose.yml` |
| Backup testado (restore verificado ponta a ponta) | ⚠️ não verificado nesta auditoria — o script existe mas seu funcionamento fim-a-fim (dump + restore) não foi exercitado |
| Retenção/rotação de backups | ⚠️ não especificado na documentação atual |

## 10. Checklist de Recuperação

| Item | Status |
| --- | --- |
| Jobs travados (`RUNNING` após crash do worker) são recuperados | ✅ verificado no código (`jobs/worker.py::_recover_stale`) e coberto por teste |
| Reinício do processo backend não perde jobs enfileirados | ✅ fila é durável (Postgres), não em memória |
| Migrações aplicadas automaticamente na subida do container | ✅ (`Dockerfile` CMD: `alembic upgrade head && uvicorn ...`) |
| Degradação graciosa: Postgres indisponível | ✅ readiness reporta `unavailable` (503), API não crasha ao subir se Postgres ficar indisponível depois (falha nas requisições que dependem do banco, mas o processo continua vivo) |
| Degradação graciosa: Redis indisponível | ✅ cache e rate limiter caem para fallback local (`services/cache.py`, `services/rate_limit.py`) |
| Degradação graciosa: Qdrant indisponível | ✅ memória semântica falha silenciosamente (log de aviso), resposta do agente continua sem esse contexto — verificado em `BaseAgent.run` e no Cognitive Pipeline (`CognitivePipeline._load_context`, corrigido nesta fase após ser pego por teste) |
| Degradação graciosa: provider de WhatsApp indisponível | ✅ retry com backoff exponencial, depois erro tratado pela fila de jobs (retry no nível de job); `/health/ready` reporta `degraded` |
| Failover entre providers de LLM | ✅ `AgentExecutor` tenta `LLM_FALLBACK_PROVIDER` uma vez quando o provider configurado levanta exceção; sem fallback configurado, comportamento idêntico ao anterior (propaga a exceção) |
| Mensagens duplicadas (redelivery de webhook) | ✅ dedup por `external_id` + constraint única no banco, com recuperação de `IntegrityError` para corrida entre requisições concorrentes — testado |
| Mensagens fora de ordem | ✅ ordenação por `provider_timestamp` do próprio gateway, não pela ordem de chegada — testado |
| Nunca fica em silêncio (falha definitiva do auto-reply) | ✅ `job.failed` aciona mensagem de desculpas via Event Bus — testado |

## 11. Limitações Conhecidas

1. **Auto-registro aberto** (`/api/auth/register` sem autenticação) — qualquer pessoa pode criar uma conta de dashboard com papel `user`. Não afeta o canal de WhatsApp diretamente, mas amplia a superfície de quem pode chamar `/api/chat`/`/api/agents/*/run` com acesso a ferramentas.
2. **`next@14.2.21`** tem CVEs conhecidas (incluindo uma classificada como crítica pelo advisory do Next.js); nenhum vetor de exploração foi identificado nesta aplicação especificamente (sem `middleware.ts`), mas é dívida de dependência a resolver.
3. **Cache/rate-limit em memória não é compartilhado entre réplicas** do backend — só relevante se o backend rodar com múltiplas instâncias e Redis cair ao mesmo tempo.
4. **Sem detecção de reuso de refresh token roubado** — reuso é rejeitado, mas não aciona revogação das demais sessões ativas do usuário.
5. **Backup não foi testado ponta a ponta** (dump + restore) nesta auditoria.
6. **Sem teste de carga formal** — capacidade sob concorrência real não foi medida.
7. **Build/execução Docker não verificados nesta auditoria** — limitação do ambiente de sandbox (sem acesso ao Docker Hub), não do projeto; recomenda-se verificação manual antes do deploy.
8. **Sem type-checking estático no backend** (nenhum mypy/pyright configurado) — mitigado por Pydantic em runtime e 92% de cobertura de teste, mas é uma lacuna de processo.
9. **Composição de resposta multi-etapa é concatenação simples**, não uma síntese fluida via LLM (`docs/fase4.2-relatorio.md` §8).
10. **`needs_confirmation` não tem mecanismo de retomada** — o pipeline pergunta e para, mas a próxima mensagem do contato não retoma automaticamente o plano pausado.
11. **Isolamento de contato (PROD-005) não cobre `search_memory`/`store_memory`/`update_contact_preference`** — apenas `send_whatsapp_message` e `find_contact` foram escopadas, por serem as duas ferramentas explicitamente identificadas na auditoria como capazes de vazar dados para fora da conversa atual ou agir sobre um destinatário arbitrário; as demais ferramentas de memória recebem `contact_id` explicitamente como argumento (já sob controle de quem monta o prompt/chamada), não como um alvo livre escolhido pelo modelo.

## 12. Roadmap da versão 1.1

Com a arquitetura congelada a partir deste gate (PROD-004 e PROD-005 já corrigidos), a v1.1 deve priorizar, nesta ordem:

1. Fechar o gap de auto-registro aberto (exigir convite/aprovação de admin, ou desativar por padrão).
2. Atualizar `next` para uma versão sem as CVEs conhecidas.
3. Testar backup/restore ponta a ponta e documentar a política de retenção.
4. Adicionar `docker build`/`docker compose up` como etapa de CI (hoje não existe).
5. Detecção de reuso de refresh token com revogação de sessão.
6. Mecanismo de retomada de plano pendente de confirmação no Cognitive Pipeline.
7. Avaliar combinar intenção+prioridade+planejamento em uma única chamada LLM, se o volume de produção justificar.
8. Pipeline de ingestão de documentos para popular `knowledge_search` com conteúdo real.
9. Teste de carga formal para estabelecer limites de capacidade conhecidos.

---

## DECISÃO FINAL

### STATUS: APROVADO PARA PRODUÇÃO

Os dois bloqueadores identificados na auditoria original foram corrigidos e verificados:

1. **PROD-004 — CORRIGIDO.** `WEBHOOK_SECRET` agora é obrigatório em produção, com o mesmo padrão fail-closed já aplicado a `JWT_SECRET` (`main.py::_validate_production_settings`), reforçado em `docker-compose.yml` (`:?`) e auto-provisionado por `scripts/setup.sh`. Coberto por 5 testes dedicados cobrindo exatamente os cenários exigidos (dev, prod, ausente, inválido, válido) mais 1 teste de não-regressão.

2. **PROD-005 — CORRIGIDO.** `send_whatsapp_message` e `find_contact` agora aplicam isolamento técnico via `ToolContext.contact_id` — um valor definido pela aplicação a partir do estado real da conversa, nunca escolhido pelo LLM. Uma conversa só pode agir sobre o seu próprio contato; sem uma conversa associada, o envio exige um contato já conhecido pelo backend. Coberto por 10 testes dedicados simulando tentativas de acesso indevido, todas corretamente negadas.

Suíte completa (246 testes), lint e migrações verificados sem regressão após as correções — ver `PRODUCTION_BLOCKERS_RESOLVED.md` para o detalhamento exato do que mudou e da validação executada. Nenhum outro item desta auditoria — arquitetura, performance, escalabilidade, confiabilidade, cobertura de testes, qualidade de documentação — impede a aprovação. As limitações remanescentes (§11) são riscos aceitos ou itens de roadmap (§12), não bloqueadores.
