# Runbook — Dario OS

Receitas passo a passo para tarefas operacionais comuns. Para diagnóstico de falhas, ver `INCIDENT_RESPONSE.md`.

## Deploy de uma atualização

```bash
cd docker
git -C .. pull
docker compose up -d --build
```

Migrações Alembic são aplicadas automaticamente na subida do container do backend — não há passo manual. Acompanhar: `docker compose logs -f backend` até ver a linha de start do uvicorn.

## Rollback de um deploy ruim

```bash
cd docker
git -C .. log --oneline -5          # identificar o commit anterior estável
git -C .. checkout <commit-anterior>
docker compose up -d --build
```

Se a atualização com problema já aplicou uma migração de banco nova, o rollback de código sozinho não desfaz o schema — avaliar se é necessário `alembic downgrade` manualmente dentro do container (`docker compose exec backend alembic downgrade -1`) antes de subir a versão anterior do código, caso o schema novo seja incompatível com o código antigo.

## Rotacionar `JWT_SECRET`

Invalida todos os tokens de acesso e refresh tokens existentes — todo usuário precisa fazer login de novo.

```bash
cd docker
NEW_SECRET=$(openssl rand -hex 32)
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=${NEW_SECRET}/" .env
docker compose up -d backend
```

## Rotacionar `WEBHOOK_SECRET`

Precisa ser trocado **nos dois lados** — no `.env` do Dario OS e na configuração do provider de WhatsApp/n8n que envia o header `X-Webhook-Token`.

```bash
cd docker
NEW_SECRET=$(openssl rand -hex 32)
sed -i "s/^WEBHOOK_SECRET=.*/WEBHOOK_SECRET=${NEW_SECRET}/" .env
docker compose up -d backend
# Atualizar o mesmo valor na configuração do gateway/n8n antes ou logo depois,
# senão os webhooks passam a ser rejeitados com 401.
```

## Trocar o provider de WhatsApp

```bash
cd docker
# Editar WHATSAPP_PROVIDER=<openwa|baileys|evolution|official> e as credenciais
# correspondentes (ver docker/.env.example) em .env
docker compose up -d backend
```

Nenhuma outra mudança de código é necessária — a troca é só configuração (ver `docs/architecture.md` e `backend/providers/whatsapp/README.md`).

## Trocar o provider de LLM

```bash
cd docker
# Editar LLM_PROVIDER=<openai|anthropic|glm|gemini|ollama> e a chave
# correspondente em .env
docker compose up -d backend
```

## Configurar failover automático de LLM

```bash
cd docker
echo "LLM_FALLBACK_PROVIDER=anthropic" >> .env   # ou outro provider já configurado
docker compose up -d backend
```

## Pausar temporariamente o auto-reply do WhatsApp

Útil durante uma investigação ou manutenção, sem derrubar o sistema inteiro.

```bash
cd docker
sed -i "s/^AUTO_REPLY_ENABLED=.*/AUTO_REPLY_ENABLED=false/" .env
docker compose up -d backend
```

Mensagens continuam sendo recebidas e persistidas normalmente; só a resposta automática é suspensa. Reverter com `AUTO_REPLY_ENABLED=true`.

## Criar o primeiro usuário admin

O primeiro usuário registrado via `POST /api/auth/register` vira automaticamente `admin`; os demais viram `user`. Não há um comando de CLI separado para isso — é feito pela própria API/dashboard.

## Verificar a saúde do sistema manualmente

```bash
curl -s https://<dominio>/api/health/ready | jq .
```

Ou, para a instância de dentro do host: `docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health/ready').read())"`.

## Inspecionar a fila de jobs

```bash
curl -s -H "Authorization: Bearer <token-admin>" https://<dominio>/api/jobs | jq .
curl -s -H "Authorization: Bearer <token-admin>" https://<dominio>/api/jobs/handlers | jq .
```

Cancelar um job específico: `POST /api/jobs/{id}/cancel` (admin).

## Consultar logs estruturados de auditoria

```bash
curl -s -H "Authorization: Bearer <token-admin>" \
  "https://<dominio>/api/logs?source=cognitive_pipeline" | jq .
```

## Escalar o worker de jobs para um container dedicado

Não é o modelo atual (o worker roda embutido no processo da API), mas a fila já é Postgres-backed com claim atômico (`SELECT ... FOR UPDATE SKIP LOCKED`) — múltiplas instâncias do backend já processam a fila com segurança sem mudança de código. Para separar fisicamente, seria necessário criar um novo `service` no `docker-compose.yml` rodando `jobs.worker` isoladamente e desativar `JOBS_ENABLED` no serviço da API — isso é uma mudança de infraestrutura fora do escopo deste release (ver `ROADMAP_v1.1.md`).

## Renovar certificado TLS manualmente

Normalmente não é necessário — o Caddy renova automaticamente antes do vencimento enquanto o volume `caddy_data` persiste e as portas 80/443 seguem acessíveis publicamente. Se precisar forçar:

```bash
cd docker
docker compose restart caddy
```
