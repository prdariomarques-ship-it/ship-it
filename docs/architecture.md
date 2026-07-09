# Arquitetura do Dario OS

## Visão geral

O Dario OS é composto por 8 containers orquestrados pelo Docker Compose:

```
                        ┌──────────┐
        HTTPS (443)     │  Caddy   │  reverse proxy + TLS automático
  ──────────────────────▶          │
                        └────┬─────┘
              ┌──────────────┼───────────────┐
              ▼              ▼               ▼
        ┌──────────┐   ┌──────────┐    ┌──────────┐
        │ Frontend │   │ Backend  │    │   n8n    │
        │ Next.js  │   │ FastAPI  │◀──▶│ workflows│
        └──────────┘   └────┬─────┘    └────┬─────┘
                            │               │
          ┌───────────┬─────┴───────┬───────┘
          ▼           ▼             ▼
     ┌─────────┐ ┌─────────┐  ┌─────────┐   ┌─────────┐
     │Postgres │ │  Redis  │  │ Qdrant  │   │WhatsApp │──▶ WhatsApp
     └─────────┘ └─────────┘  └─────────┘   │provider │
                                            └─────────┘
```

## Camadas (Clean Architecture)

| Camada | Diretórios | Responsabilidade |
| --- | --- | --- |
| Apresentação | `api/`, `*/router.py`, `webhooks/` | HTTP, validação Pydantic, status codes |
| Aplicação | `auth/service`, `chat/service`, `jobs/service`, `memory/contact_memory`, `agents/` | Casos de uso e orquestração |
| Domínio | `models/` | Entidades (SQLAlchemy 2, tipagem forte) |
| Acesso a dados | `repositories/` | Repository pattern; nenhuma query fora daqui ou da fábrica CRUD |
| Infraestrutura | `providers/`, `database/`, `memory/service`, `services/`, `jobs/worker` | Vendors, banco, Redis, Qdrant |

### Padrões aplicados

- **Repository Pattern** — `SQLAlchemyRepository[T]` genérico + repositórios especializados (`ContactRepository.get_or_create_by_phone`, `JobRepository.due_jobs`, ...). Rotas e serviços não montam queries.
- **Dependency Injection** — `Depends(get_db)`, `Depends(get_auth_service)`, `CurrentUser`; os factories de provider são funções puras substituíveis em teste.
- **Factory Pattern** — `providers/llm/factory.py`, `providers/whatsapp/factory.py`, `agents/registry.py`: seleção por configuração, sem `if` espalhado.
- **Strategy Pattern** — contratos `LLMProvider` e `WhatsAppProvider`; cada vendor é uma estratégia intercambiável (inclusive normalização de webhook por provider).
- **Service Layer** — regras de negócio (rotação de refresh token, resumo de contato, enfileiramento) vivem em serviços, não em rotas.
- **Open/Closed** — novo agente = subclasse registrada; novo provider = classe + entrada no factory; novo job = decorator `@job_handler`.

## Providers

```
providers/
  llm/        base.py (LLMProvider, ChatMessage, ToolSpec, LLMResult)
    openai/     chat completions + tools + embeddings
    anthropic/  messages API + tool_use (sem embeddings — EmbeddingsNotSupportedError)
    glm/        endpoint OpenAI-compatível da Zhipu
  whatsapp/   base.py (WhatsAppProvider, InboundMessage)
    openwa/     wa-automate easy-api
    evolution/  Evolution API (message/sendText etc.)
    baileys/    gateway REST sobre a lib Baileys
    official/   WhatsApp Cloud API (Meta Graph)
```

`LLM_PROVIDER` e `EMBEDDING_PROVIDER` são independentes porque nem todo vendor tem API de embeddings (Anthropic não tem; GLM usa dimensões incompatíveis com a coleção). Sem chave configurada os providers degradam para respostas stub — o sistema continua de pé.

## Agentes

Um agente é composto por:

- **system prompt** — identidade e regras;
- **tools** — `Tool` = JSON Schema + handler async com `ToolContext(db, user)`; resultados voltam ao modelo como JSON;
- **memory** — busca semântica no Qdrant injetada no contexto pelo planner;
- **planner** (`agents/planner.py`) — monta a lista de mensagens (prompt + memórias + pedido);
- **executor** (`agents/executor.py`) — loop de function calling: modelo → tool calls → resultados → ... até resposta final ou orçamento de iterações (`AGENT_MAX_ITERATIONS`).

O executor registra cada passo (`steps` na resposta da API), o que dá auditabilidade às ações dos agentes.

## Memória por contato

1. Toda mensagem (entrada/saída) vira embedding no Qdrant (`payload: content, source, contact_id`) com metadados auditáveis na tabela `embeddings`.
2. `last_interaction_at` é atualizado a cada interação.
3. A cada `CONTACT_SUMMARY_EVERY_N_MESSAGES` mensagens, o job `contact.summarize` pede ao LLM um resumo do histórico recente e grava em `contacts.summary`.
4. Agentes recebem memórias relevantes via busca semântica (filtrável por contato) e podem gravar novas com a tool `store_memory`.

## Fila de jobs

- Tabela `jobs` (durável) + worker assíncrono iniciado no lifespan da API.
- `scheduled_at` permite agendamento; retry com backoff exponencial (`JOBS_RETRY_BACKOFF_SECONDS * 2^tentativa`) até `max_attempts`, depois `failed` com `last_error`.
- Eventos de ciclo de vida (started/succeeded/retry_scheduled/failed) são publicados no canal Redis `darioos:jobs:events` e persistidos em `logs`.
- Por ser Postgres-backed, workers adicionais podem rodar em containers separados sem mudar o lado que enfileira.

## Autenticação e permissões

- Access token JWT curto (30 min) + refresh token rotativo de 30 dias.
- Refresh tokens armazenados como hash SHA-256; rotação revoga o anterior; reuso de token revogado é rejeitado (mitiga replay).
- RBAC: papel `admin` (primeiro usuário) e `user`; `require_roles(...)` protege rotas administrativas (`/api/logs`, `/api/jobs`).

## Migrações

Alembic com `env.py` async lendo `DATABASE_URL` das settings. O container do backend executa `alembic upgrade head` antes do uvicorn. Autogenerate: `alembic revision --autogenerate -m "..."`.

## Observabilidade

- **Liveness** `/health`, **readiness** `/health/ready` (Postgres obrigatório; Redis/Qdrant marcam `degraded`).
- **Métricas** `/metrics` (Prometheus): `darioos_http_requests_total{method,path,status}` e `darioos_http_request_duration_seconds` com o template da rota (baixa cardinalidade).
- **Logs estruturados** em JSON (`LOG_JSON=true`), um objeto por linha, prontos para Loki/ELK.
- **Auditoria** na tabela `logs` (webhooks, eventos de jobs).

## Decisões e trade-offs

- Worker de jobs no mesmo processo da API por padrão (simplicidade); a fila durável permite extrair para container dedicado quando a carga justificar.
- O webhook do WhatsApp é público por necessidade; proteja-o na borda (rede Docker/Caddy) e prefira providers com autenticação de webhook.
- O provider Baileys pressupõe um gateway REST na frente da lib Node; o layout de endpoints é configurável via `BAILEYS_BASE_URL`.
