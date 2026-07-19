# Backup — Dario OS

## O que existe hoje

`scripts/backup.sh` cobre **PostgreSQL e Qdrant**:

- **PostgreSQL**: `pg_dump` plano, comprimido com `gzip`.
- **Qdrant**: um snapshot por coleção (descoberta dinamicamente via `GET /collections`, não hardcoded), via a própria API de snapshot do Qdrant — consistente num ponto no tempo, sem precisar parar o container. O snapshot é criado dentro do volume do Qdrant, copiado para fora com `docker cp` (o Qdrant não publica sua porta pro host, e sua imagem não tem `curl`/`wget` — as chamadas HTTP à API do Qdrant passam pelo container do `backend`, que já está na mesma rede) e apagado de dentro do container logo em seguida, pra não acumular snapshot sobre snapshot no próprio volume.
- Destino padrão: `$HOME/darioos-backups` (configurável via `BACKUP_DIR`).
- Retenção: mantém os 14 mais recentes de cada tipo (configurável via `RETENTION`), aplicada por coleção no caso do Qdrant.
- **Agendamento: automático.** `scripts/install-backup-timer.sh` instala e ativa um `systemd --user` timer (`docker/systemd/darioos-backup.{service,timer}`) rodando todo dia às 03:00 (com `Persistent=true` — se a máquina estiver desligada/suspensa nesse horário, roda assim que ligar de novo). Confirme que está ativo com `systemctl --user list-timers darioos-backup.timer`.

## O que NÃO é coberto pelo backup automático (decisão, não lacuna)

| Volume | Conteúdo | Por que não é coberto |
| --- | --- | --- |
| `redis_data` | Cache e janelas de rate limit | Puramente efêmero por design — `cache_service` já degrada para um fallback em memória quando o Redis está fora do ar (ver `docs/architecture.md`). Nada durável vive ali. |
| `openwa_data` | Perfil do Chromium usado pela sessão do WhatsApp | O próprio diretório é prefixado `_IGNORE_session` pela biblioteca (confirmado dentro do container em execução) — ela mesma sinaliza que é cache/perfil descartável. Não há mecanismo de exportação de sessão configurado neste deployment. Perdê-lo significa re-parear o WhatsApp (escanear o QR de novo), não perder dado — as mensagens já estão no Postgres. |
| `n8n_data` | Workflows configurados no n8n | Sem automação real configurada lá neste ambiente até agora (o Cognitive Pipeline nativo não depende do n8n). Se isso mudar, adicionar ao `backup.sh` é direto — mesmo padrão de `docker cp` de um volume. |
| `caddy_data` / `caddy_config` | Certificados TLS | Recuperável automaticamente (Caddy reemite na próxima subida). |

## Verificação de backup

Depois de qualquer execução, confirme que os arquivos não estão vazios e que o dump do Postgres é íntegro:

```bash
gunzip -t "$BACKUP_DIR"/darioos-*.sql.gz && echo "Postgres íntegro"
```

Não há verificação automática de checksum do snapshot do Qdrant além do que a própria API do Qdrant já reporta na criação (`checksum` no retorno de `POST .../snapshots`).

## Restauração

Ver `RESTORE.md` — `scripts/restore.sh` automatiza a restauração de ambos (Postgres e Qdrant), com confirmação obrigatória antes de sobrescrever dados atuais.
