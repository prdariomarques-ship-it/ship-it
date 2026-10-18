#!/bin/bash
# Vigia de linhas: reversão segura. Uso:  bash rollback_linewatch.sh   (na mesma pasta do aplicar_na_vps_linewatch.sh). Reinicia o backend.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
CFG=/app/utils/config.py; MAIN=/app/main.py; SVC=/app/services/line_watch.py; JOB=/app/jobs/line_watch_job.py
ESPERA_HEALTH=${ESPERA_HEALTH:-90}
die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
trap 'docker exec "$BK" rm -f "$CFG.lw_rb" "$MAIN.lw_rb" >/dev/null 2>&1 || true' EXIT
[ -s hashes_antes_linewatch.txt ] || die "falta hashes_antes_linewatch.txt (gerado na aplicação)"
for f in config.py:$CFG main.py:$MAIN; do
  n=${f%%:*}; p=${f#*:}
  want=$(awk -v n="$n" '$2==n{print $1}' hashes_antes_linewatch.txt)
  expect "$n.orig" "$(sha_file $n.orig)" "$want"
  docker cp "$n.orig" "$BK:$p.lw_rb"
  expect "$n temporário" "$(sha_live $p.lw_rb)" "$want"
done
# 1º apaga a corrente de jobs (enquanto o módulo ainda existe), depois troca os arquivos
docker exec -i "$BK" python - <<'PY' || die "não consegui apagar os jobs lines.watch (nada foi trocado)"
import asyncio
from sqlalchemy import delete
from database.session import async_session_factory
from models.job import Job, JobStatus

async def run():
    async with async_session_factory() as s:
        r = await s.execute(delete(Job).where(Job.name == "lines.watch", Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])))
        await s.commit(); print("jobs lines.watch removidos:", r.rowcount)
asyncio.run(run())
PY
docker exec "$BK" sh -c "set -e; mv $CFG.lw_rb $CFG; mv $MAIN.lw_rb $MAIN; rm -f $SVC $JOB"
for f in config.py:$CFG main.py:$MAIN; do
  n=${f%%:*}; p=${f#*:}
  expect "$n final" "$(sha_live $p)" "$(awk -v n="$n" '$2==n{print $1}' hashes_antes_linewatch.txt)"
done
docker restart "$BK" >/dev/null
i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && break; sleep 1; i=$((i+1)); done
[ "$(health)" = healthy ] || die "o backend não ficou healthy depois da reversão (docker logs $BK)"
echo "REVERTIDO: config.py/main.py voltaram ao original, módulos removidos, jobs apagados; backend reiniciado e healthy."
echo "Obs.: se o vigia rodou entre a leitura e a troca, um job pode ter sido recriado: rode de novo se aparecer erro 'handler desconhecido' no log."
