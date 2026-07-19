#!/usr/bin/env bash
# Daily backup of PostgreSQL and Qdrant. Keeps the last $RETENTION backups of
# each. Scheduled via a systemd --user timer (see
# scripts/install-backup-timer.sh and docs/systemd/darioos-backup.*) rather
# than a manually-registered cron entry, per this project's convention for
# background jobs (WSL).
#
# Redis and the OpenWA session volume are intentionally NOT backed up here:
# - Redis is pure cache + Event Bus pub/sub fanout — cache_service already
#   degrades to an in-memory fallback when Redis is unreachable, so nothing
#   durable actually lives there.
# - OpenWA's session directory is prefixed `_IGNORE_session` by the library
#   itself (confirmed inside the running container) — it's Chromium
#   profile/cache, regenerable via a QR re-scan. No separate session-export
#   mechanism is configured in this deployment. Losing it means re-pairing
#   WhatsApp, not losing data (messages already live in Postgres).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/darioos-backups}"
RETENTION="${RETENTION:-14}"
STAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

cd "$(dirname "$0")/../docker"

# --- PostgreSQL ---------------------------------------------------------
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-dario}" "${POSTGRES_DB:-darioos}" \
  | gzip > "$BACKUP_DIR/darioos-$STAMP.sql.gz"

ls -1t "$BACKUP_DIR"/darioos-*.sql.gz | tail -n +"$((RETENTION + 1))" | xargs -r rm --

# --- Qdrant (vector memory) ----------------------------------------------
# One snapshot per collection, discovered dynamically rather than hardcoded.
# Qdrant's snapshot API produces a point-in-time consistent export without
# needing to stop the container. The snapshot file is created inside
# qdrant's own volume, then pulled out with `docker cp` (goes through the
# Docker daemon, not the network — qdrant's port isn't published to the
# host) and deleted from the container afterward so its volume doesn't
# accumulate every snapshot ever taken on top of what's already exported
# here. Routed through the backend container's Python because qdrant's own
# image has neither curl nor wget.
collections=$(docker compose exec -T backend python3 -c "
import json, urllib.request
data = json.loads(urllib.request.urlopen('http://qdrant:6333/collections', timeout=10).read())
print('\n'.join(c['name'] for c in data['result']['collections']))
")

qdrant_container=$(docker compose ps -q qdrant)

for collection in $collections; do
  snapshot_name=$(docker compose exec -T backend python3 -c "
import json, urllib.request
req = urllib.request.Request('http://qdrant:6333/collections/$collection/snapshots', method='POST')
data = json.loads(urllib.request.urlopen(req, timeout=30).read())
print(data['result']['name'])
")

  docker cp "$qdrant_container:/qdrant/snapshots/$collection/$snapshot_name" \
    "$BACKUP_DIR/qdrant-$collection-$STAMP.snapshot"

  docker compose exec -T backend python3 -c "
import urllib.request
req = urllib.request.Request('http://qdrant:6333/collections/$collection/snapshots/$snapshot_name', method='DELETE')
urllib.request.urlopen(req, timeout=10)
"

  ls -1t "$BACKUP_DIR"/qdrant-"$collection"-*.snapshot | tail -n +"$((RETENTION + 1))" | xargs -r rm --
done

echo "Backup salvo em $BACKUP_DIR — Postgres: darioos-$STAMP.sql.gz; Qdrant: $(echo "$collections" | wc -l) coleção(ões) em qdrant-*-$STAMP.snapshot"
