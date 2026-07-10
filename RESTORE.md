# Restore — Dario OS

Não existe um script de restore automatizado hoje (`scripts/restore.sh` não existe — ver `ROADMAP_v1.1.md`, item de backlog). Este documento é o procedimento manual atual.

## Antes de começar

1. Confirme qual backup será restaurado e sua integridade (`gunzip -t arquivo.sql.gz`).
2. Avise os usuários/operador: o sistema ficará indisponível durante a restauração.
3. Se possível, faça um backup do estado atual antes de sobrescrever (mesmo que esteja corrompido/desatualizado — evita perder qualquer coisa recuperável).

## Restaurar o PostgreSQL

```bash
cd docker

# Parar o backend para não haver escrita concorrente durante o restore
docker compose stop backend

# Recriar o banco vazio (CUIDADO: apaga os dados atuais do Postgres)
docker compose exec -T postgres psql -U "${POSTGRES_USER:-dario}" -c \
  "DROP DATABASE IF EXISTS ${POSTGRES_DB:-darioos}; CREATE DATABASE ${POSTGRES_DB:-darioos};"

# Restaurar o dump
gunzip -c /caminho/para/darioos-YYYYMMDD-HHMMSS.sql.gz | \
  docker compose exec -T postgres psql -U "${POSTGRES_USER:-dario}" "${POSTGRES_DB:-darioos}"

# Subir o backend de novo — ele roda `alembic upgrade head` automaticamente no start,
# então se o dump for de uma versão de schema mais antiga, as migrações pendentes
# são aplicadas nesse momento
docker compose up -d backend
```

Depois de subir, confirme com `GET /health/ready` que o Postgres está `ok` e que `alembic upgrade head` não falhou (`docker compose logs backend`).

## Restaurar o Qdrant (memória permanente)

Se você tem um snapshot (ver `BACKUP.md`):

```bash
cd docker
docker compose stop qdrant
docker run --rm -v darioos_qdrant_data:/data -v /caminho/do/backup:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/qdrant-snapshot.tar.gz -C /data"
docker compose start qdrant
```

**Sem um snapshot**: não há como recuperar embeddings/memória semântica perdida — o histórico estruturado (mensagens, contatos) no Postgres continua intacto, mas a busca semântica e o contexto de longo prazo dos agentes ficam vazios a partir desse ponto. O sistema continua funcionando (a busca semântica falha graciosamente — ver `docs/architecture.md`), só sem o contexto acumulado.

## Restaurar a sessão do WhatsApp (OpenWA)

Se você tem um snapshot do volume `openwa_data` (ver `BACKUP.md`):

```bash
cd docker
docker compose stop openwa
docker run --rm -v darioos_openwa_data:/data -v /caminho/do/backup:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/openwa-session.tar.gz -C /data"
docker compose start openwa
```

**Sem um snapshot** (o caso mais comum, já que não há backup automático desse volume): a sessão precisa ser re-autenticada do zero — suba o container normalmente e re-escaneie o QR code pelo fluxo padrão do OpenWA. O número de WhatsApp fica temporariamente indisponível até esse passo manual.

## Restaurar n8n (workflows)

```bash
cd docker
docker compose stop n8n
docker run --rm -v darioos_n8n_data:/data -v /caminho/do/backup:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/n8n-data.tar.gz -C /data"
docker compose start n8n
```

Sem snapshot: os workflows configurados no n8n precisam ser recriados manualmente. Não afeta o fluxo nativo do Cognitive Pipeline (que não depende do n8n).

## Verificação pós-restore

Checklist mínimo depois de qualquer restauração:

1. `GET /health/ready` retorna `status: "ok"` (ou `"degraded"` apenas nos componentes esperados, nunca `"unavailable"`).
2. Login no dashboard funciona com uma conta existente.
3. `GET /api/contacts` (autenticado) retorna dados esperados — confirma que o Postgres foi restaurado corretamente.
4. Enviar uma mensagem de teste pelo WhatsApp e confirmar que o auto-reply funciona ponta a ponta — confirma que o provider/sessão está ativo.
5. Conferir `docker compose logs backend` por qualquer erro de migração ou de conexão.

## Teste de restore

Este release não incluiu um teste de restore ponta a ponta em ambiente real (ver `PRODUCTION_APPROVAL.md` §9/§11). Recomenda-se validar este procedimento manualmente em um ambiente de staging antes de depender dele em um incidente real.
