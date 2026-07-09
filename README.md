# Dario OS

Sistema operacional pessoal baseado em IA — centraliza WhatsApp, agenda, tarefas, loja, igreja, memória permanente e automações em uma única plataforma, tudo executando em Docker.

## Início rápido

```bash
./scripts/setup.sh
```

O script cria `docker/.env` (com `JWT_SECRET` gerado automaticamente) e sobe toda a stack. Depois:

| Serviço | URL |
| --- | --- |
| Dashboard | http://localhost |
| API + Swagger | http://localhost/docs |
| ReDoc | http://localhost/redoc |
| Métricas Prometheus | http://localhost/metrics |
| n8n (automações) | http://localhost/n8n/ |

Edite `docker/.env` para configurar o provedor de LLM (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` ou `GLM_API_KEY`), o provedor de WhatsApp, senha do banco e o domínio (com um domínio real o Caddy provisiona HTTPS automaticamente). As migrações Alembic rodam automaticamente na subida do backend.

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | FastAPI (Python 3.12, SQLAlchemy 2 async, Alembic) |
| Frontend | Next.js 14 (App Router, TypeScript) |
| Banco | PostgreSQL 16 |
| Memória vetorial | Qdrant |
| Cache / filas / eventos | Redis |
| Automação | n8n |
| WhatsApp | OpenWA, Baileys, Evolution API ou WhatsApp Cloud API (plugável) |
| IA | OpenAI, Anthropic ou GLM (plugável) |
| Autenticação | JWT + Refresh Token rotativo + RBAC |
| Observabilidade | Logs estruturados, Prometheus, health/readiness |
| Reverse proxy | Caddy (HTTPS automático) |
| Containers | Docker Compose |

## Arquitetura

O backend segue Clean Architecture com camadas explícitas e desacopladas:

```
Rotas (FastAPI)  →  Serviços (casos de uso)  →  Repositórios  →  Banco
       │                    │
       │                    └──→ Providers (LLM / WhatsApp) — Strategy + Factory
       │
       └──→ Agentes (planner + executor + tools + memória)
```

- **Repository Pattern** (`repositories/`) — todo acesso a dados passa por repositórios; o genérico `SQLAlchemyRepository` cobre CRUD e os especializados adicionam consultas de domínio.
- **Service Layer** (`auth/service.py`, `chat/service.py`, `jobs/service.py`, `memory/`) — casos de uso ficam fora das rotas.
- **Dependency Injection** — sessões, serviços e usuário autenticado entram via `Depends`; nada instancia infraestrutura dentro de rota.
- **Factory + Strategy** (`providers/*/factory.py`, `agents/registry.py`) — provedores e agentes são resolvidos por configuração.

```
backend/
  api/            # Rotas CRUD (fábrica genérica) + dashboard + whatsapp
  auth/           # JWT, refresh token rotativo, RBAC (admin/user), service layer
  agents/         # BaseAgent + planner + executor + tools (function calling)
  chat/           # Orquestração de conversa (agente + memória)
  memory/         # Memória permanente (Qdrant) + memória por contato
  jobs/           # Fila durável: agendamento, retry exponencial, eventos, worker
  providers/
    llm/          # openai / anthropic / glm  (contrato LLMProvider)
    whatsapp/     # openwa / baileys / evolution / official  (contrato WhatsAppProvider)
  repositories/   # Repository pattern (genérico + especializados)
  observability/  # health/readiness, métricas Prometheus
  services/       # cache Redis, rate limit, auditoria
  webhooks/       # Entrada do WhatsApp (payload normalizado pelo provider)
  workflows/      # Integração n8n
  database/       # Engine async + base declarativa
  models/         # users, contacts, messages, church_members, store_customers,
                  # notes, calendar, tasks, embeddings, logs, refresh_tokens, jobs
  alembic/        # Migrações
  tests/          # 46 testes pytest
```

## Fluxo de execução (WhatsApp)

```
WhatsApp → Provider (OpenWA/Baileys/Evolution/Official)
        → POST /api/webhooks/whatsapp        (payload normalizado pelo provider)
        → persiste contato + mensagem + embedding (memória do contato)
        → fila de jobs → n8n (workflow "whatsapp-inbound", com retry)
        → n8n chama /api/chat (agente assistant: planner → tools → resposta)
        → /api/whatsapp/send-text → Provider → WhatsApp
```

A cada N mensagens (configurável) um job `contact.summarize` atualiza o resumo automático do contato via LLM. Cada contato acumula: resumo automático, histórico, embeddings, preferências, tags e última interação.

## Agentes

| Agente | Função | Ferramentas |
| --- | --- | --- |
| `personal` | Agenda, lembretes, notas, resumos | tarefas, eventos, notas, memória |
| `church` | Oração, escalas, cultos, avisos, versículos | membros, pedidos de oração, eventos, memória |
| `store` | Produtos, pedidos, clientes, orçamentos | clientes, contatos, memória |
| `content` | Conteúdo para redes sociais | notas, memória |
| `assistant` | Atende o WhatsApp; acesso a todos os domínios | todas + envio de WhatsApp |

Cada agente possui **system prompt**, **tools** (function calling sobre os serviços da API), **memory** (busca semântica no Qdrant injetada no contexto), **planner** (monta o contexto) e **executor** (loop plan → act → observe com orçamento de iterações).

### Como adicionar um novo agente

1. Crie `backend/agents/meu_agent.py` com uma subclasse de `BaseAgent` definindo `name`, `description`, `system_prompt` e `tools`.
2. Precisa de ferramentas novas? Declare-as em `backend/agents/tools/` (um `Tool` = JSON Schema + handler async que recebe `ToolContext`).
3. Registre a classe em `agents/registry.py`. Pronto: aparece em `GET /api/agents` e no `/api/chat`.

### Como adicionar um novo provedor

- **LLM**: crie `providers/llm/<nome>/provider.py` implementando `LLMProvider` (`chat` com tools + `embed`), registre no dicionário de `providers/llm/factory.py` e selecione com `LLM_PROVIDER=<nome>`.
- **WhatsApp**: crie `providers/whatsapp/<nome>/provider.py` implementando `WhatsAppProvider` (5 métodos de envio + `parse_webhook` normalizando para `InboundMessage`), registre em `providers/whatsapp/factory.py` e selecione com `WHATSAPP_PROVIDER=<nome>`.

Nenhuma outra parte da aplicação muda — rotas, agentes e jobs dependem apenas dos contratos.

## Autenticação

- `POST /api/auth/register` — o primeiro usuário vira `admin`, os demais `user`.
- `POST /api/auth/login` — retorna `access_token` (curto) + `refresh_token` (rotativo, armazenado como hash SHA-256).
- `POST /api/auth/refresh` — rotaciona: o token antigo é revogado e um novo par é emitido; reuso de token revogado é rejeitado.
- `POST /api/auth/logout` — revoga o refresh token.
- Rotas administrativas (`/api/logs`, `/api/jobs`) exigem papel `admin` (`require_roles`).

## Fila de jobs

Fila durável em Postgres processada por um worker assíncrono: agendamento (`delay_seconds`), retry com backoff exponencial, eventos publicados no Redis (`darioos:jobs:events`) e persistidos na tabela `logs`. Handlers registrados por decorator:

```python
from jobs.registry import job_handler

@job_handler("meu.job")
async def handler(db: AsyncSession, payload: dict) -> None: ...
```

Gerencie pela API admin: `GET/POST /api/jobs`, `POST /api/jobs/{id}/cancel`, `GET /api/jobs/handlers`.

## Observabilidade

- `GET /health` / `GET /health/live` — liveness.
- `GET /health/ready` — readiness com verificação de Postgres (obrigatório), Redis e Qdrant (degradam sem derrubar).
- `GET /metrics` — Prometheus (contadores e histograma de latência por rota).
- `LOG_JSON=true` — logs estruturados em JSON (padrão no Docker Compose).

## Desenvolvimento

```bash
# Backend + frontend com hot reload, sem Docker
./scripts/dev.sh

# Testes (59 testes; cobertura ~86%)
cd backend && pip install -r requirements-dev.txt && pytest
pytest --cov=. --cov-report=term    # com cobertura

# CI: GitHub Actions roda lint + testes + migrações (backend) e build (frontend) em cada PR

# Migrações
cd backend
alembic upgrade head                        # aplicar
alembic revision --autogenerate -m "..."    # criar a partir dos models
```

## Segurança

- JWT curto + refresh token rotativo (hash em banco, revogável; expirados são purgados)
- RBAC com papéis `admin`/`user`
- `WEBHOOK_SECRET`: quando definido, o webhook de entrada exige `X-Webhook-Token`
- Em produção o backend se recusa a subir com `JWT_SECRET` fraca/padrão
- HTTPS automático + headers de segurança via Caddy
- Rate limit por IP (Redis, com fallback em memória; probes de health/metrics isentos)
- Senhas com PBKDF2-SHA256 salteado, verificadas fora do event loop e em tempo constante
- Backup diário: agende `scripts/backup.sh` no cron (`0 3 * * *`)

## Documentação

- [docs/architecture.md](docs/architecture.md) — arquitetura, camadas e decisões
- [docs/api.md](docs/api.md) — visão geral dos endpoints (referência completa no Swagger em `/docs`)
