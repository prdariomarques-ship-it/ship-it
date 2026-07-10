# Backup — Dario OS

## O que existe hoje

`scripts/backup.sh` faz um dump do **PostgreSQL apenas**:

```bash
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-dario}" "${POSTGRES_DB:-darioos}" \
  | gzip > "$BACKUP_DIR/darioos-$STAMP.sql.gz"
```

- Formato: `pg_dump` plano, comprimido com `gzip`.
- Destino padrão: `$HOME/darioos-backups` (configurável via `BACKUP_DIR`).
- Retenção: mantém os 14 dumps mais recentes (configurável via `RETENTION`), os mais antigos são apagados automaticamente pelo próprio script.
- Agendamento: **não é automático** — precisa ser registrado manualmente no cron do host (o comentário no topo do script já sugere `0 3 * * *`, mas isso não está configurado em nenhum lugar do repositório).

## O que NÃO é coberto pelo backup automático

Isto é importante e não estava documentado antes deste release: `backup.sh` cobre apenas o Postgres. Os demais volumes nomeados do Docker Compose (`docker/docker-compose.yml`) não têm backup automatizado:

| Volume | Conteúdo | Impacto se perdido |
| --- | --- | --- |
| `qdrant_data` | **Memória permanente semântica** (embeddings de conversas, conhecimento) | Perda de toda a memória de longo prazo dos contatos — o histórico estruturado no Postgres continua, mas a busca semântica e o contexto acumulado somem |
| `openwa_data` | Sessão autenticada do WhatsApp (provider padrão) | Necessário re-parear o dispositivo (escanear o QR code novamente) — o número de WhatsApp fica offline até isso ser feito manualmente |
| `n8n_data` | Workflows e credenciais configuradas no n8n | Perda de todas as automações externas configuradas (só relevante para quem usa `workflow.trigger`) |
| `redis_data` | Cache e janelas de rate limit | Sem impacto de dados permanentes — é projetado para ser efêmero (o sistema já degrada graciosamente sem Redis, ver `docs/architecture.md`) |
| `caddy_data` / `caddy_config` | Certificados TLS emitidos pelo Let's Encrypt | Recuperável automaticamente (Caddy reemite na próxima subida), só custa uma pequena janela sem HTTPS válido |

## Procedimento de backup completo recomendado (manual, até um script existir)

Além de `scripts/backup.sh`, faça um snapshot dos volumes críticos periodicamente:

```bash
cd docker

# Qdrant (memória permanente) — snapshot da API do próprio Qdrant
curl -X POST http://localhost:6333/collections/darioos_memory/snapshots
# O snapshot fica dentro do volume qdrant_data; copie-o para fora do host também.

# OpenWA (sessão do WhatsApp) — parar o container antes de copiar para evitar
# corrupção de arquivos de sessão em uso
docker compose stop openwa
docker run --rm -v darioos_openwa_data:/data -v "$BACKUP_DIR":/backup alpine \
  tar czf /backup/openwa-session-$(date +%Y%m%d).tar.gz -C /data .
docker compose start openwa

# n8n (workflows)
docker run --rm -v darioos_n8n_data:/data -v "$BACKUP_DIR":/backup alpine \
  tar czf /backup/n8n-data-$(date +%Y%m%d).tar.gz -C /data .
```

(Nomes exatos dos volumes podem variar conforme o nome do projeto Compose — confirme com `docker volume ls`.)

## Verificação de backup

Nenhuma verificação automática de integridade existe hoje. Recomendação mínima até isso ser automatizado: após cada backup, confirmar que o arquivo não está vazio e que `gunzip -t` não reporta erro:

```bash
gunzip -t "$BACKUP_DIR"/darioos-*.sql.gz && echo "backup íntegro"
```

O procedimento de restauração completo (com teste de restore) está em `RESTORE.md`. Este release **não** incluiu um teste de restore ponta a ponta — ver `PRODUCTION_APPROVAL.md` §11 e `ROADMAP_v1.1.md`.
