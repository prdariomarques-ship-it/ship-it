#!/bin/bash
# Libera áudio b2b-sales: reversão segura. Uso:  bash rollback_b2b.sh   (na mesma pasta do aplicar_na_vps_b2b.sh). Reinicia o backend.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
CFG=/app/utils/config.py; PRV=/app/providers/whatsapp/evolution/provider.py
ESPERA_HEALTH=${ESPERA_HEALTH:-90}
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
trap 'docker exec "$BK" rm -f "$CFG.b2b_rb" "$PRV.b2b_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes_b2b.txt ] || die "falta hashes_antes_b2b.txt (gerado na aplicação)"
for f in config.py:$CFG provider.py:$PRV; do
  n=${f%%:*}; p=${f#*:}
  want=$(awk -v n="$n" '$2==n{print $1}' hashes_antes_b2b.txt)
  expect "$n.orig" "$(sha_file $n.orig)" "$want"
  docker cp "$n.orig" "$BK:$p.b2b_rb"
  expect "$n temporário" "$(sha_live $p.b2b_rb)" "$want"
done
docker exec "$BK" sh -c "set -e; mv $CFG.b2b_rb $CFG; mv $PRV.b2b_rb $PRV"
for f in config.py:$CFG provider.py:$PRV; do
  n=${f%%:*}; p=${f#*:}
  expect "$n final" "$(sha_live $p)" "$(awk -v n="$n" '$2==n{print $1}' hashes_antes_b2b.txt)"
done
docker restart "$BK" >/dev/null
i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && break; sleep 1; i=$((i+1)); done
[ "$(health)" = healthy ] || die "o backend não ficou healthy depois da reversão (docker logs $BK)"
echo "REVERTIDO: config.py e provider.py voltaram ao estado anterior; o áudio da b2b-sales volta a ser ignorado."
