#!/bin/bash
# Guarda do dono: reversão segura. Uso:  bash rollback_ownerguard.sh   (na mesma pasta do aplicar_na_vps_ownerguard.sh). Reinicia o backend.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
SVC=/app/services/line_watch.py; JOB=/app/jobs/line_watch_job.py; OAM=/app/services/owner_activity.py; HND=/app/jobs/handlers.py; WIN=/app/owner_activity_windows.txt
ESPERA_HEALTH=${ESPERA_HEALTH:-90}
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
trap 'docker exec "$BK" rm -f "$SVC.og_rb" "$JOB.og_rb" "$HND.og_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes_ownerguard.txt ] || die "falta hashes_antes_ownerguard.txt (gerado na aplicação)"
for f in line_watch.py:$SVC line_watch_job.py:$JOB handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  want=$(awk -v n="$n" '$2==n{print $1}' hashes_antes_ownerguard.txt)
  expect "$n.orig" "$(sha_file $n.orig)" "$want"
  docker cp "$n.orig" "$BK:$p.og_rb"
  expect "$n temporário" "$(sha_live $p.og_rb)" "$want"
done
docker exec "$BK" sh -c "set -e; mv $SVC.og_rb $SVC; mv $JOB.og_rb $JOB; mv $HND.og_rb $HND; rm -f $OAM"
[ -f janelas_criadas_ownerguard.txt ] && docker exec "$BK" rm -f "$WIN"
for f in line_watch.py:$SVC line_watch_job.py:$JOB handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  expect "$n final" "$(sha_live $p)" "$(awk -v n="$n" '$2==n{print $1}' hashes_antes_ownerguard.txt)"
done
docker restart "$BK" >/dev/null
i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && break; sleep 1; i=$((i+1)); done
[ "$(health)" = healthy ] || die "o backend não ficou healthy depois da reversão (docker logs $BK)"
echo "REVERTIDO: handlers.py e o vigia voltaram ao estado anterior; guarda do dono removida; backend reiniciado e healthy."
