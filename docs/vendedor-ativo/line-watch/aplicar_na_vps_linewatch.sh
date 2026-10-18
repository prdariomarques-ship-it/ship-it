#!/bin/bash
# Vigia das linhas do WhatsApp: aplicação segura no container do backend. Uso:  bash aplicar_na_vps_linewatch.sh   (na pasta com os 3 arquivos .py)
# Muda config.py e main.py (edições ancoradas), cria services/line_watch.py e jobs/line_watch_job.py, REINICIA o backend (segundos) e semeia a
# 1ª rodada do job lines.watch. NÃO envia nenhuma mensagem durante a aplicação: a verificação só LÊ o estado das linhas no Evolution.
# Qualquer falha devolve arquivos, apaga os jobs semeados e reinicia de novo.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
CFG=/app/utils/config.py; MAIN=/app/main.py; SVC=/app/services/line_watch.py; JOB=/app/jobs/line_watch_job.py
SVC_SHA_ESPERADO=f6b6d5e1a6d0c8bea50293d5b24530ccb5edcd4861b1dce0c618d4d5ccb1a79c
JOB_SHA_ESPERADO=e9ccfa2659bc350d3f7e24f80b61ea782b741f70024daeeec95bafaed121674e
ESPERA_HEALTH=${ESPERA_HEALTH:-90}
export LW_INSTANCES="${LW_INSTANCES:-MARQUESCOLOR,b2b-sales,azusa-church,Dário Marques Neto}"

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { local i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
PYDEL='from sqlalchemy import delete
import asyncio
from database.session import async_session_factory
from models.job import Job, JobStatus
async def run():
    async with async_session_factory() as s:
        r = await s.execute(delete(Job).where(Job.name == "lines.watch", Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])))
        await s.commit(); print("jobs lines.watch removidos:", r.rowcount)
asyncio.run(run())'
trap 'docker exec "$BK" rm -f "$CFG.lw_new" "$MAIN.lw_new" "$SVC.lw_new" "$JOB.lw_new" >/dev/null 2>&1 || true' EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  docker exec -i "$BK" python -c "$PYDEL" >/dev/null 2>&1 || echo "ATENÇÃO: não consegui apagar os jobs semeados (rode o rollback_linewatch.sh)"
  docker cp config.py.orig "$BK:$CFG" || echo "ATENÇÃO: falha ao copiar config.py"
  docker cp main.py.orig "$BK:$MAIN" || echo "ATENÇÃO: falha ao copiar main.py"
  docker exec "$BK" rm -f "$SVC" "$JOB" || true
  docker restart "$BK" >/dev/null || echo "ATENÇÃO: falha ao reiniciar"
  wait_healthy && echo "backend healthy de novo" || echo "ATENÇÃO: backend não ficou healthy; rode rollback_linewatch.sh e olhe docker logs"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. confere os arquivos desta pasta e lê os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_linewatch.py ] && [ -s line_watch.py ] && [ -s line_watch_job.py ] || die "faltam arquivos nesta pasta"
expect "line_watch.py desta pasta" "$(sha_file line_watch.py)" "$SVC_SHA_ESPERADO"
expect "line_watch_job.py desta pasta" "$(sha_file line_watch_job.py)" "$JOB_SHA_ESPERADO"
docker exec "$BK" test ! -e "$SVC" || die "$SVC já existe no container (vigia já aplicado?)"
docker exec "$BK" test ! -e "$JOB" || die "$JOB já existe no container"
for f in config.py:$CFG main.py:$MAIN; do
  n=${f%%:*}; p=${f#*:}
  docker cp "$BK:$p" "$n.lido"; [ -s "$n.lido" ] || die "não consegui ler $p"
  expect "$n (cópia fiel)" "$(sha_live $p)" "$(sha_file $n.lido)"
done
echo "OK"

echo "== 2. telefone que recebe o alerta"
PHONE="${LW_PHONE:-}"
[ -n "$PHONE" ] || PHONE=$(docker exec "$BK" printenv WHATSAPP_OWNER_ALERT_PHONE 2>/dev/null || true)
if [ -z "$PHONE" ]; then read -rp "Telefone que vai RECEBER o alerta (só dígitos, com DDI, ex.: 5511912345678): " PHONE; fi
PHONE=${PHONE//[^0-9]/}
export LW_PHONE="$PHONE"
echo "OK (termina em ${PHONE: -4})"

echo "== 3. gera os arquivos novos (aborta sem tocar em nada se uma âncora não bater)"
python3 aplicar_linewatch.py . || die "o aplicar_linewatch.py recusou (nada foi gravado no container)"
for n in config.py main.py; do mv "$n.lido" "$n.orig"; printf '%s  %s\n' "$(sha_file $n.orig)" "$n" >> hashes_antes_linewatch.tmp; done
mv hashes_antes_linewatch.tmp hashes_antes_linewatch.txt
echo "OK (originais guardados como *.orig)"

echo "== 4. copia para nomes temporários e confere (o código em uso não muda)"
docker cp config.py.novo "$BK:$CFG.lw_new"; docker cp main.py.novo "$BK:$MAIN.lw_new"; docker cp line_watch.py "$BK:$SVC.lw_new"; docker cp line_watch_job.py "$BK:$JOB.lw_new"
expect "config temporário" "$(sha_live $CFG.lw_new)" "$(sha_file config.py.novo)"
expect "main temporário" "$(sha_live $MAIN.lw_new)" "$(sha_file main.py.novo)"
expect "line_watch temporário" "$(sha_live $SVC.lw_new)" "$SVC_SHA_ESPERADO"
expect "line_watch_job temporário" "$(sha_live $JOB.lw_new)" "$JOB_SHA_ESPERADO"
echo "OK"

echo "== 5. troca (cópias de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $CFG $CFG.lw_bak; cp -p $MAIN $MAIN.lw_bak; mv $CFG.lw_new $CFG; mv $MAIN.lw_new $MAIN; mv $SVC.lw_new $SVC; mv $JOB.lw_new $JOB"; then back_out "a troca falhou"; fi
expect "config final" "$(sha_live $CFG)" "$(sha_file config.py.novo)"
expect "main final" "$(sha_live $MAIN)" "$(sha_file main.py.novo)"
echo "OK"

echo "== 6. reinicia o backend e espera ficar healthy"
docker restart "$BK" >/dev/null || back_out "o restart falhou"
wait_healthy || back_out "o backend não ficou healthy em ${ESPERA_HEALTH}s"
echo "OK"

echo "== 7. verificação funcional (só LÊ o estado das linhas; não envia mensagem)"
docker exec -i -e LW_PHONE="$PHONE" "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import asyncio, os
from jobs import line_watch_job
from services import line_watch
from utils.config import get_settings

s = get_settings()
assert s.line_watch_enabled is True and s.line_watch_alert_phone == os.environ["LW_PHONE"], "configuração não carregou"
names = line_watch.watched_instances(s)
assert len(names) >= 2, names
states = asyncio.run(line_watch.fetch_states(names, base_url=s.evolution_base_url, api_key=s.evolution_api_key))
for n in names:
    print("  linha", n, "->", states[n])
assert any(v != "unreachable" for v in states.values()), "o Evolution não respondeu para nenhuma linha"
print("vigia carregado; linhas:", ", ".join(names))
PY
echo "OK"

echo "== 8. semeia a primeira rodada do job (idempotente)"
docker exec -i "$BK" python - <<'PY' || back_out "não consegui semear o job"
import asyncio
from database.session import async_session_factory
from jobs.line_watch_job import JOB_NAME, start
from repositories.job import JobRepository

async def run():
    async with async_session_factory() as s:
        await start(s)
        assert await JobRepository(s).pending_by_name(JOB_NAME) is not None, "job não foi criado"
    print("job lines.watch semeado")
asyncio.run(run())
PY
echo "OK"
echo "SUCESSO: vigia ligado. A 1ª rodada roda em instantes; você será avisado (no WhatsApp ${PHONE: -4}) se alguma linha ficar fora do ar por ~4 min. Para desfazer: bash rollback_linewatch.sh"
