#!/usr/bin/env bash
# Daily backup of PostgreSQL (schedule with cron: 0 3 * * * /path/to/backup.sh).
# Keeps the last 14 dumps.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/darioos-backups}"
RETENTION="${RETENTION:-14}"
STAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

cd "$(dirname "$0")/../docker"

docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-dario}" "${POSTGRES_DB:-darioos}" \
  | gzip > "$BACKUP_DIR/darioos-$STAMP.sql.gz"

# Prune old dumps beyond the retention window
ls -1t "$BACKUP_DIR"/darioos-*.sql.gz | tail -n +"$((RETENTION + 1))" | xargs -r rm --

echo "Backup salvo em $BACKUP_DIR/darioos-$STAMP.sql.gz"
