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
| API + OpenAPI docs | http://localhost/docs |
| n8n (automações) | http://localhost/n8n/ |

Edite `docker/.env` para configurar `OPENAI_API_KEY` (respostas de IA e embeddings), senha do banco e o domínio (com um domínio real o Caddy provisiona HTTPS automaticamente).

## Stack

| Camada | Tecnologia |
| --- | --- |
| Backend | FastAPI (Python 3.12, SQLAlchemy 2 async) |
| Frontend | Next.js 14 (App Router, TypeScript) |
| Banco | PostgreSQL 16 |
| Memória vetorial | Qdrant |
| Cache / rate limit | Redis |
| Automação | n8n |
| WhatsApp | OpenWA (wa-automate) |
| IA | OpenAI API |
| Autenticação | JWT (Bearer) |
| Reverse proxy | Caddy (HTTPS automático) |
| Containers | Docker Compose |

## Estrutura

```
backend/
  api/        # Rotas CRUD (contatos, tarefas, agenda, notas, igreja, loja, logs, dashboard, whatsapp)
  auth/       # JWT, hash de senha, registro/login
  chat/       # Orquestração de conversa (agente + memória + LLM)
  memory/     # Memória permanente (embeddings OpenAI + Qdrant)
  workflows/  # Integração com n8n
  agents/     # Agentes: personal, whatsapp, church, store, content
  webhooks/   # Webhook de entrada do WhatsApp (OpenWA)
  database/   # Engine/base SQLAlchemy async
  models/     # Tabelas: users, contacts, messages, church_members, store_customers,
              #          notes, calendar, tasks, embeddings, logs
  services/   # OpenAI, OpenWA, rate limit (Redis), auditoria
  utils/      # Config (pydantic-settings) e logging
  tests/      # Suíte pytest (auth, CRUD, webhook, agentes)
frontend/
  app/        # Páginas: início, conversas, agenda, tarefas, loja, igreja, analytics, logs, configurações, login
  components/ # Sidebar, tabelas, cards
  hooks/      # useApi (fetch autenticado)
  styles/     # CSS global
docker/       # docker-compose.yml, Caddyfile, .env.example
scripts/      # setup.sh, dev.sh, backup.sh (backup diário via cron)
docs/         # Arquitetura e API
```

## Fluxo do WhatsApp

```
WhatsApp → OpenWA → POST /api/webhooks/whatsapp → (persiste contato + mensagem)
        → n8n (workflow "whatsapp-inbound") → Agente IA + memória (Qdrant)
        → POST /api/whatsapp/send-text → OpenWA → WhatsApp
```

## Agentes

| Agente | Função |
| --- | --- |
| `personal` | Agenda, lembretes, notas, pesquisa, resumos |
| `whatsapp` | Recebe e responde mensagens (texto, imagem, PDF, áudio, localização) |
| `church` | Pedidos de oração, escalas, cultos, avisos, versículos |
| `store` | Produtos, pedidos, clientes, estoque, orçamentos |
| `content` | Conteúdo para Instagram, Facebook, YouTube, TikTok, LinkedIn |

Cada agente é um prompt especializado com acesso à memória permanente. Novos agentes: crie uma subclasse de `BaseAgent` e registre em `agents/registry.py`.

## Desenvolvimento

```bash
# Backend + frontend com hot reload, sem Docker
./scripts/dev.sh

# Testes do backend
cd backend && pip install -r requirements-dev.txt && pytest
```

## Segurança

- JWT em todas as rotas (exceto health e webhook de entrada)
- HTTPS automático via Caddy quando `DOMAIN` é um domínio real
- Rate limit por IP (Redis, com fallback em memória)
- Senhas com PBKDF2-SHA256 salteado
- Backup diário: agende `scripts/backup.sh` no cron (`0 3 * * *`)

## Documentação

- [docs/architecture.md](docs/architecture.md) — arquitetura e decisões de projeto
- [docs/api.md](docs/api.md) — visão geral dos endpoints (a referência completa é o OpenAPI em `/docs`)
