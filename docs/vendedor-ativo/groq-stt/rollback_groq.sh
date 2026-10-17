#!/bin/bash
# Groq STT: reversão segura. Uso:  bash rollback_groq.sh   (na mesma pasta do aplicar_na_vps_groq.sh). Reinicia o backend.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
CFG=/app/utils/config.py; FAC=/app/providers/stt/factory.py; RTR=/app/webhooks/router.py; GRQ=/app/providers/stt/groq.py; ENVF=/app/.env
ESPERA_HEALTH=${ESPERA_HEALTH:-90}
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
trap 'docker exec "$BK" rm -f "$CFG.groq_rb" "$FAC.groq_rb" "$RTR.groq_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes_groq.txt ] || die "falta hashes_antes_groq.txt (gerado na aplicação)"
for f in config.py:$CFG factory.py:$FAC router.py:$RTR; do
  n=${f%%:*}; p=${f#*:}
  want=$(awk -v n="$n" '$2==n{print $1}' hashes_antes_groq.txt)
  expect "$n.orig" "$(sha_file $n.orig)" "$want"
  docker cp "$n.orig" "$BK:$p.groq_rb"
  expect "$n temporário" "$(sha_live $p.groq_rb)" "$want"
done
docker exec "$BK" sh -c "set -e; mv $CFG.groq_rb $CFG; mv $FAC.groq_rb $FAC; mv $RTR.groq_rb $RTR; rm -f $GRQ"
if [ -f env_criado_groq.txt ]; then
  docker exec "$BK" rm -f "$ENVF"
elif docker exec "$BK" test -f "$ENVF.groq_bak"; then
  docker exec "$BK" sh -c "cp -p $ENVF.groq_bak $ENVF"
fi
for f in config.py:$CFG factory.py:$FAC router.py:$RTR; do
  n=${f%%:*}; p=${f#*:}
  expect "$n final" "$(sha_live $p)" "$(awk -v n="$n" '$2==n{print $1}' hashes_antes_groq.txt)"
done
docker restart "$BK" >/dev/null
i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && break; sleep 1; i=$((i+1)); done
[ "$(health)" = healthy ] || die "o backend não ficou healthy depois da reversão (docker logs $BK)"
echo "REVERTIDO: arquivos e .env voltaram ao estado anterior ao Groq; backend reiniciado e healthy."
