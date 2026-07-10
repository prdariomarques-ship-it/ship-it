# Operações — Dario OS

Guia de referência para operar o Dario OS em produção continuamente após o lançamento da v1.0. Este documento descreve **o estado real do sistema hoje** — não propõe mudanças de arquitetura ou funcionalidades novas.

## Topologia de serviços

O sistema roda como 8 containers Docker Compose (`docker/docker-compose.yml`), todos na rede `darioos`:

| Serviço | Papel | Porta exposta ao host |
| --- | --- | --- |
| `caddy` | Reverse proxy + TLS automático (Let's Encrypt) | 80, 443 |
| `backend` | API FastAPI + worker de jobs embutido | nenhuma (só via Caddy) |
| `frontend` | Dashboard Next.js | nenhuma (só via Caddy) |
| `postgres` | Banco de dados principal | nenhuma (rede interna) |
| `redis` | Cache + rate limit + fan-out do Event Bus | nenhuma (rede interna) |
| `qdrant` | Memória semântica (vetores) | nenhuma (rede interna) |
| `n8n` | Automações externas opcionais | nenhuma (via `/n8n/` no Caddy) |
| `openwa` | Gateway do provider de WhatsApp padrão | nenhuma (rede interna) |

Nenhum serviço além do Caddy expõe porta diretamente ao host — todo tráfego externo passa pelo reverse proxy.

## Ciclo de vida do backend

- **Migrações**: aplicadas automaticamente na subida do container (`Dockerfile` CMD: `alembic upgrade head && uvicorn ...`). Não há passo manual.
- **Worker de jobs**: roda embutido no mesmo processo da API (`jobs.worker.job_worker`), iniciado/parado no lifespan do FastAPI. Não é um container separado hoje.
- **Health checks**: `GET /health` e `/health/live` (liveness, sempre `200`), `GET /health/ready` (readiness — Postgres obrigatório, Redis/Qdrant/WhatsApp degradam sem derrubar; `503` só se o Postgres estiver fora). O `Dockerfile` já declara um `HEALTHCHECK` batendo em `/health`.
- **Logs**: sempre em `stdout` (nunca em arquivo), formato texto ou JSON (`LOG_JSON=true`, padrão no Compose) — consumidos pelo driver de log do Docker. Ver `MONITORING.md` para rotação.

## Iniciar / parar / atualizar

```bash
cd docker

# Subir tudo (primeira vez: ./scripts/setup.sh faz isso e gera os secrets)
docker compose up -d --build

# Ver logs em tempo real
docker compose logs -f backend

# Reiniciar só o backend (ex: após mudar uma variável de ambiente)
docker compose restart backend

# Aplicar uma atualização de código (nova imagem)
git pull
docker compose up -d --build

# Parar tudo (mantém os volumes/dados)
docker compose down

# Parar e apagar TODOS os dados (destrutivo — nunca em produção sem backup)
docker compose down -v
```

Procedimentos passo a passo para cenários específicos: ver `RUNBOOK.md`.

## Variáveis de ambiente

Configuradas em `docker/.env` (nunca commitado — ver `docker/.env.example` para o template). As obrigatórias em produção (o backend recusa subir sem elas — ver `main.py::_validate_production_settings`):

| Variável | Obrigatória em produção | Gerada automaticamente por `setup.sh`? |
| --- | --- | --- |
| `JWT_SECRET` | Sim (≥ 32 chars) | Sim |
| `WEBHOOK_SECRET` | Sim (≥ 32 chars) | Sim |
| `POSTGRES_PASSWORD` | Não obrigatória tecnicamente, mas **deve** ser trocada do padrão (`change-me` no `.env.example`) | Não — editar manualmente |
| Chave do provedor de LLM (`OPENAI_API_KEY` etc.) | Não bloqueia o boot, mas sem ela o sistema responde com uma mensagem de stub | Não |

Todas as demais variáveis têm um default seguro e são opcionais. Referência completa: `README.md` (seção "Segurança" e tabelas de configuração) e `docker/.env.example` (comentado).

## Escopo deste documento

Este arquivo é o índice operacional. Para procedimentos específicos, ver:

- `BACKUP.md` — o que é (e o que não é) coberto pelo backup automático.
- `RESTORE.md` — como restaurar a partir de um backup.
- `MONITORING.md` — o que está instrumentado hoje e como observar o sistema.
- `INCIDENT_RESPONSE.md` — como reagir a falhas conhecidas.
- `RUNBOOK.md` — receitas passo a passo para tarefas operacionais comuns.
- `MAINTENANCE_PLAN.md` — rotinas periódicas recomendadas.
