#!/bin/bash
# Mudança 3 (texto): reversão segura. Uso:  bash rollback_m3a.sh   (na mesma pasta do aplicar_na_vps_m3a.sh)
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
PA=/app/agents/prompts/darius_twin.md
PB=/app/agents/prompts/twin_conversation.md
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
trap 'docker exec "$BK" rm -f "$PA.m3a_rb" "$PB.m3a_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes.txt ] || die "falta hashes_antes.txt (gerado na aplicação)"
A_ORIG=$(awk '/darius_twin.md/{print $1}' hashes_antes.txt); B_ORIG=$(awk '/twin_conversation.md/{print $1}' hashes_antes.txt)
expect "darius_twin.md.orig" "$(sha_file darius_twin.md.orig)" "$A_ORIG"
expect "twin_conversation.md.orig" "$(sha_file twin_conversation.md.orig)" "$B_ORIG"
docker cp darius_twin.md.orig "$BK:$PA.m3a_rb"
docker cp twin_conversation.md.orig "$BK:$PB.m3a_rb"
expect "darius_twin temporário" "$(sha_live $PA.m3a_rb)" "$A_ORIG"
expect "twin_conversation temporário" "$(sha_live $PB.m3a_rb)" "$B_ORIG"
docker exec "$BK" sh -c "set -e; mv $PA.m3a_rb $PA; mv $PB.m3a_rb $PB"
expect "darius_twin.md" "$(sha_live $PA)" "$A_ORIG"
expect "twin_conversation.md" "$(sha_live $PB)" "$B_ORIG"
echo "REVERTIDO: os textos do Twin voltaram aos de antes da Mudança 3."
