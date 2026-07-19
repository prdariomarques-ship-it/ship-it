#!/usr/bin/env bash
# Restore PostgreSQL and/or Qdrant from a backup created by scripts/backup.sh.
# DESTRUCTIVE — overwrites current data. Requires typing a confirmation
# phrase; there is no --yes/force flag on purpose.
#
# Usage:
#   scripts/restore.sh --postgres /path/to/darioos-TIMESTAMP.sql.gz
#   scripts/restore.sh --qdrant /path/to/qdrant-COLLECTION-TIMESTAMP.snapshot
#   scripts/restore.sh --postgres X.sql.gz --qdrant Y.snapshot
#
# n8n workflows and the OpenWA session are not covered — backup.sh doesn't
# back those up either (see its header for why). Restoring those, if you
# have your own manual backup, means stopping the container and replacing
# its volume directly — see RESTORE.md.
set -euo pipefail

POSTGRES_FILE=""
QDRANT_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --postgres) POSTGRES_FILE="$2"; shift 2 ;;
    --qdrant) QDRANT_FILE="$2"; shift 2 ;;
    *) echo "Argumento desconhecido: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$POSTGRES_FILE" && -z "$QDRANT_FILE" ]]; then
  echo "Uso: $0 [--postgres arquivo.sql.gz] [--qdrant arquivo.snapshot]" >&2
  exit 1
fi

cd "$(dirname "$0")/../docker"

echo "ATENÇÃO: isto vai sobrescrever dados atuais."
[[ -n "$POSTGRES_FILE" ]] && echo "  PostgreSQL <- $POSTGRES_FILE"
[[ -n "$QDRANT_FILE" ]] && echo "  Qdrant <- $QDRANT_FILE"
read -r -p "Digite 'restaurar' para confirmar: " confirm
if [[ "$confirm" != "restaurar" ]]; then
  echo "Cancelado."
  exit 1
fi

if [[ -n "$POSTGRES_FILE" ]]; then
  echo "Verificando integridade do dump..."
  gunzip -t "$POSTGRES_FILE"

  echo "Parando backend..."
  docker compose stop backend

  echo "Recriando banco vazio..."
  docker compose exec -T postgres psql -U "${POSTGRES_USER:-dario}" -c \
    "DROP DATABASE IF EXISTS ${POSTGRES_DB:-darioos}; CREATE DATABASE ${POSTGRES_DB:-darioos};"

  echo "Restaurando dump..."
  gunzip -c "$POSTGRES_FILE" \
    | docker compose exec -T postgres psql -U "${POSTGRES_USER:-dario}" "${POSTGRES_DB:-darioos}"

  echo "Subindo backend (roda 'alembic upgrade head' automaticamente)..."
  docker compose up -d backend
fi

if [[ -n "$QDRANT_FILE" ]]; then
  filename=$(basename "$QDRANT_FILE")
  # Expects the naming backup.sh produces: qdrant-<collection>-<timestamp>.snapshot
  collection=$(echo "$filename" | sed -E 's/^qdrant-(.+)-[0-9]{8}-[0-9]{6}\.snapshot$/\1/')
  if [[ "$collection" == "$filename" ]]; then
    echo "Não consegui extrair o nome da coleção de '$filename' — renomeie para o padrão qdrant-<colecao>-<timestamp>.snapshot." >&2
    exit 1
  fi

  qdrant_container=$(docker compose ps -q qdrant)
  target_dir="/qdrant/snapshots/$collection"

  docker compose exec -T qdrant mkdir -p "$target_dir"
  docker cp "$QDRANT_FILE" "$qdrant_container:$target_dir/$filename"

  echo "Restaurando coleção '$collection' a partir do snapshot..."
  docker compose exec -T backend python3 -c "
import json, urllib.request
body = json.dumps({'location': 'file://$target_dir/$filename'}).encode()
req = urllib.request.Request(
    'http://qdrant:6333/collections/$collection/snapshots/recover',
    data=body, method='PUT', headers={'Content-Type': 'application/json'},
)
print(urllib.request.urlopen(req, timeout=120).read().decode())
"
fi

cat <<'EOF'

Restore concluído. Verificação recomendada (RESTORE.md):
  1. GET /health/ready deve responder status "ok"
  2. Login no dashboard com uma conta existente
  3. GET /api/contacts (autenticado) retorna dado esperado
  4. Enviar uma mensagem de teste pelo WhatsApp, se o Qdrant/Postgres foram restaurados
EOF
