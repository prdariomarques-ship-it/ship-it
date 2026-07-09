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
     │Postgres │ │  Redis  │  │ Qdrant  │   │ OpenWA  │──▶ WhatsApp
     └─────────┘ └─────────┘  └─────────┘   └─────────┘
```

## Camadas do backend (Clean Architecture)

| Camada | Diretórios | Responsabilidade |
| --- | --- | --- |
| Apresentação | `api/`, `auth/router`, `chat/router`, `memory/router`, `agents/router`, `webhooks/`, `workflows/router` | Rotas HTTP, validação (Pydantic), status codes |
| Aplicação | `chat/service`, `agents/`, `services/` | Orquestração de casos de uso |
| Domínio | `models/` | Entidades e regras (SQLAlchemy 2, tipagem forte) |
| Infraestrutura | `database/`, `memory/service`, `services/openai_service`, `services/whatsapp_service`, `services/rate_limit` | Postgres, Qdrant, OpenAI, OpenWA, Redis |

Princípios aplicados:

- **Inversão de dependência** — rotas dependem de serviços injetados (`Depends`), serviços encapsulam clientes externos atrás de interfaces simples.
- **Single responsibility** — cada módulo do spec (`auth`, `chat`, `memory`, `workflows`, `agents`, `webhooks`) tem um papel único.
- **Open/closed** — novos agentes são subclasses de `BaseAgent` registradas no `agents/registry.py`; novos CRUDs usam a fábrica `api/crud.py`.
- **Degradação graciosa** — sem `OPENAI_API_KEY` o sistema responde com stub; sem Redis o rate limit cai para memória local; sem n8n o webhook persiste a mensagem e loga o erro.

## Fluxo de mensagem do WhatsApp

1. OpenWA recebe a mensagem e faz POST em `/api/webhooks/whatsapp`.
2. O backend cria/atualiza o **contato**, persiste a **mensagem** e grava um **log**.
3. Em background, o evento normalizado é encaminhado ao n8n (workflow `whatsapp-inbound`).
4. O n8n chama de volta a API (`/api/chat` ou `/api/agents/whatsapp/run`), que busca memórias no Qdrant e gera a resposta com a OpenAI.
5. O n8n envia a resposta com `/api/whatsapp/send-text` (ou mídia), que registra a mensagem de saída e chama o OpenWA.

## Memória permanente

- Cada informação relevante é embeddada (`text-embedding-3-small`) e gravada no Qdrant com payload `{content, source, contact_id}`.
- Os metadados ficam na tabela `embeddings` do Postgres (fonte da verdade auditável).
- A busca é semântica (`/api/memory/search?q=...`), com filtro opcional por contato — é assim que os agentes personalizam respostas.

## Segurança

- **JWT** HS256 com expiração; senhas com PBKDF2-SHA256 (390k iterações, salt aleatório).
- **Rate limit** fixed-window por IP no middleware (Redis compartilhado entre workers).
- **HTTPS** automático pelo Caddy (Let's Encrypt) quando `DOMAIN` é público.
- **Backups** diários do Postgres via `scripts/backup.sh` + cron, com retenção de 14 dias.

## Decisões e trade-offs

- `init_db()` cria as tabelas no startup por simplicidade; quando o schema estabilizar, migrar para Alembic.
- O webhook do WhatsApp é público por necessidade (OpenWA não assina requests); proteja-o na borda (Caddy) restringindo a rede Docker, e/ou configure `OPENWA_API_KEY`.
- Agentes são prompt-based nesta fase; a evolução natural é dar-lhes ferramentas (function calling) sobre os próprios endpoints CRUD.
