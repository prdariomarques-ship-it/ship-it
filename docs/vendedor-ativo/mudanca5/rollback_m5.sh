#!/bin/bash
# Mudança 5 (texto): reversão segura. Uso:  bash rollback_m5.sh   (na mesma pasta do aplicar_na_vps_m5.sh)
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
PB=/app/agents/prompts/twin_conversation.md
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
trap 'docker exec "$BK" rm -f "$PB.m5_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes_m5.txt ] || die "falta hashes_antes_m5.txt (gerado na aplicação)"
B_ORIG=$(awk '/twin_conversation.md/{print $1}' hashes_antes_m5.txt)
expect "twin_conversation.md.orig" "$(sha_file twin_conversation.md.orig)" "$B_ORIG"
docker cp twin_conversation.md.orig "$BK:$PB.m5_rb"
expect "twin_conversation temporário" "$(sha_live $PB.m5_rb)" "$B_ORIG"
docker exec "$BK" sh -c "set -e; mv $PB.m5_rb $PB"
expect "twin_conversation.md" "$(sha_live $PB)" "$B_ORIG"
echo "REVERTIDO: o texto do Twin voltou ao de antes da Mudança 5."
