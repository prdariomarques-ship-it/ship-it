#!/bin/bash
# Mudança 4: reversão segura. Uso:  bash rollback_na_vps_m4.sh   (na mesma pasta do aplicar_na_vps_m4.sh)
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
H_ORIG=bf3ff6b771721ace8bde9cc3e525f80593f4511f2c88c47de4c92fdd438fc117
HP=/app/jobs/handlers.py
LP=/app/twin_silent_contacts.txt
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
trap 'docker exec "$BK" rm -f "$HP.m4_rb" >/dev/null 2>&1 || true' EXIT

echo "== 1. confere o original guardado"
expect "handlers.py.orig" "$(sha_file handlers.py.orig)" "$H_ORIG"
echo "== 2. copia para nome temporário, confere e troca"
docker cp handlers.py.orig "$BK:$HP.m4_rb"
expect "handlers temporário" "$(sha_live $HP.m4_rb)" "$H_ORIG"
docker exec "$BK" sh -c "set -e; mv $HP.m4_rb $HP"
expect "handlers.py" "$(sha_live $HP)" "$H_ORIG"
echo "== 3. reinicia e espera ficar healthy (máx. 150 s)"
docker restart "$BK" >/dev/null
for _ in $(seq 1 30); do sleep 5; [ "$(health)" = healthy ] && break; done
[ "$(health)" = healthy ] || die "o container não ficou healthy; chame o suporte antes de qualquer outra ação"
expect "handlers.py final" "$(sha_live $HP)" "$H_ORIG"
docker exec "$BK" python -c "import jobs.handlers; print('imports ok')"
echo "REVERTIDO: o backend voltou ao handlers.py de antes da Mudança 4 (a lista $LP continua no container, sem efeito)."
