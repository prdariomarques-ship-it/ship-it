#!/bin/bash
# Gemeo (papeis/silencio/ato proibido): reversao segura. Uso:  bash rollback_twin.sh   (na mesma pasta do aplicar_na_vps_twin.sh). Reinicia o backend.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
TW=/app/agents/darius_twin.py; HND=/app/jobs/handlers.py; ROL=/app/agents/darius_twin_roles.py; ACT=/app/agents/darius_twin_actions.py; SIL=/app/orchestrator/twin_silence.py
ESPERA_HEALTH=${ESPERA_HEALTH:-90}
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
trap 'docker exec "$BK" rm -f "$TW.tw_rb" "$HND.tw_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes_twin.txt ] || die "falta hashes_antes_twin.txt (gerado na aplicacao)"
for f in darius_twin.py:$TW handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  want=$(awk -v n="$n" '$2==n{print $1}' hashes_antes_twin.txt)
  expect "$n.orig" "$(sha_file $n.orig)" "$want"
  docker cp "$n.orig" "$BK:$p.tw_rb"
  expect "$n temporario" "$(sha_live $p.tw_rb)" "$want"
done
docker exec "$BK" sh -c "set -e; mv $TW.tw_rb $TW; mv $HND.tw_rb $HND; rm -f $ROL $ACT $SIL"
for f in darius_twin.py:$TW handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  expect "$n final" "$(sha_live $p)" "$(awk -v n="$n" '$2==n{print $1}' hashes_antes_twin.txt)"
done
docker restart "$BK" >/dev/null
i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && break; sleep 1; i=$((i+1)); done
[ "$(health)" = healthy ] || die "o backend nao ficou healthy depois da reversao (docker logs $BK)"
echo "REVERTIDO: darius_twin.py e handlers.py voltaram ao estado anterior; modulos novos removidos; backend reiniciado e healthy."
