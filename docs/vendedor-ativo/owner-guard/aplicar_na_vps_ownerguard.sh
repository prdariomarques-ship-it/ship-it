#!/bin/bash
# Guarda de atividade do dono (loja, B2B, Azusa) + alerta ao dono por outra linha. Uso:  bash aplicar_na_vps_ownerguard.sh
# (na pasta com aplicar_owner_guard.py, owner_activity.py, line_watch.py, line_watch_job.py). REINICIA o backend (segundos). NÃO envia mensagens.
# Cria services/owner_activity.py, atualiza o vigia (2 arquivos), faz 6 edições ancoradas no jobs/handlers.py e cria /app/owner_activity_windows.txt
# (janelas por agente; editável sem reiniciar). Qualquer falha devolve tudo e reinicia de novo.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
SVC=/app/services/line_watch.py; JOB=/app/jobs/line_watch_job.py; OAM=/app/services/owner_activity.py; HND=/app/jobs/handlers.py; WIN=/app/owner_activity_windows.txt
OLD_SVC=f6b6d5e1a6d0c8bea50293d5b24530ccb5edcd4861b1dce0c618d4d5ccb1a79c
OLD_JOB=e9ccfa2659bc350d3f7e24f80b61ea782b741f70024daeeec95bafaed121674e
NEW_SVC=ccf2203bb641fa849c35c095f3d32a2e2590a900bc7083edf012fdbc5479dd89
NEW_JOB=21ac90687208fec800ea9ba9135bf908a940a57d12a11e4eb5f24e8cc1e5e07a
OA_SHA=63285e777d9a68c54c4b1bd392aa487150d638fe17254a2f2fbc9bef1dfdc5b9
ESPERA_HEALTH=${ESPERA_HEALTH:-90}

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { local i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
trap 'docker exec "$BK" rm -f "$SVC.og_new" "$JOB.og_new" "$OAM.og_new" "$HND.og_new" >/dev/null 2>&1 || true' EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  docker cp line_watch.py.orig "$BK:$SVC" || echo "ATENÇÃO: falha ao copiar line_watch.py"
  docker cp line_watch_job.py.orig "$BK:$JOB" || echo "ATENÇÃO: falha ao copiar line_watch_job.py"
  docker cp handlers.py.orig "$BK:$HND" || echo "ATENÇÃO: falha ao copiar handlers.py"
  docker exec "$BK" rm -f "$OAM" || true
  [ "${WIN_CRIADO:-0}" = 1 ] && { docker exec "$BK" rm -f "$WIN" || true; }
  docker restart "$BK" >/dev/null || echo "ATENÇÃO: falha ao reiniciar"
  wait_healthy && echo "backend healthy de novo" || echo "ATENÇÃO: backend não ficou healthy; rode rollback_ownerguard.sh e olhe docker logs"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. confere os arquivos desta pasta e lê os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_owner_guard.py ] && [ -s owner_activity.py ] && [ -s line_watch.py ] && [ -s line_watch_job.py ] || die "faltam arquivos nesta pasta"
expect "owner_activity.py desta pasta" "$(sha_file owner_activity.py)" "$OA_SHA"
expect "line_watch.py desta pasta" "$(sha_file line_watch.py)" "$NEW_SVC"
expect "line_watch_job.py desta pasta" "$(sha_file line_watch_job.py)" "$NEW_JOB"
docker exec "$BK" test ! -e "$OAM" || die "$OAM já existe no container (guarda já aplicada?)"
for f in line_watch.py:$SVC line_watch_job.py:$JOB handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  docker cp "$BK:$p" "$n.lido"; [ -s "$n.lido" ] || die "não consegui ler $p"
  expect "$n (cópia fiel)" "$(sha_live $p)" "$(sha_file $n.lido)"
done
expect "line_watch.py do container é a versão do vigia aplicado" "$(sha_file line_watch.py.lido)" "$OLD_SVC"
expect "line_watch_job.py do container é a versão do vigia aplicado" "$(sha_file line_watch_job.py.lido)" "$OLD_JOB"
python3 aplicar_owner_guard.py . || die "o aplicar_owner_guard.py recusou (nada foi gravado no container)"
for n in line_watch.py line_watch_job.py handlers.py; do mv "$n.lido" "$n.orig"; printf '%s  %s\n' "$(sha_file $n.orig)" "$n" >> hashes_antes_ownerguard.tmp; done
mv hashes_antes_ownerguard.tmp hashes_antes_ownerguard.txt
WIN_CRIADO=0; docker exec "$BK" test ! -e "$WIN" && { WIN_CRIADO=1; echo criado > janelas_criadas_ownerguard.txt; } || true
echo "OK (originais guardados como *.orig)"

echo "== 2. copia para nomes temporários e confere (o código em uso não muda)"
docker cp owner_activity.py "$BK:$OAM.og_new"; docker cp line_watch.py "$BK:$SVC.og_new"; docker cp line_watch_job.py "$BK:$JOB.og_new"; docker cp handlers.py.novo "$BK:$HND.og_new"
expect "owner_activity temporário" "$(sha_live $OAM.og_new)" "$OA_SHA"
expect "line_watch temporário" "$(sha_live $SVC.og_new)" "$NEW_SVC"
expect "line_watch_job temporário" "$(sha_live $JOB.og_new)" "$NEW_JOB"
expect "handlers temporário" "$(sha_live $HND.og_new)" "$(sha_file handlers.py.novo)"
echo "OK"

echo "== 3. troca (cópias de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $SVC $SVC.og_bak; cp -p $JOB $JOB.og_bak; cp -p $HND $HND.og_bak; mv $SVC.og_new $SVC; mv $JOB.og_new $JOB; mv $HND.og_new $HND; mv $OAM.og_new $OAM"; then back_out "a troca falhou"; fi
if [ "$WIN_CRIADO" = 1 ]; then
  printf '# Janela (segundos) em que o dono "está ativo" depois de escrever/enviar mídia: o agente fica calado. 0 desliga. Lido a cada decisão; não precisa reiniciar.\ndefault=360\nb2b=360\nazusa=360\nstore=360\n' | docker exec -i "$BK" sh -c "cat > $WIN" || back_out "não consegui criar $WIN"
fi
expect "handlers final" "$(sha_live $HND)" "$(sha_file handlers.py.novo)"
echo "OK"

echo "== 4. reinicia o backend e espera ficar healthy"
docker restart "$BK" >/dev/null || back_out "o restart falhou"
wait_healthy || back_out "o backend não ficou healthy em ${ESPERA_HEALTH}s"
echo "OK"

echo "== 5. verificação funcional (só LÊ; não envia mensagem)"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import asyncio
import jobs.handlers  # noqa: F401  (importa sem erro com as edições)
from database.session import async_session_factory
from services import line_watch, owner_activity as oa
from utils.config import get_settings

assert oa.window_for("b2b") > 0 and oa.window_for("store") > 0
print("janelas:", {a: oa.window_for(a) for a in ("b2b", "azusa", "store")})
s = get_settings()
assert line_watch.route_owner_alert("5500000000000", None, s) is None          # número que não é do dono: nunca redireciona
async def run():
    async with async_session_factory() as db:
        # leitura real: o dono teve atividade nos últimos 3 dias no contato 154 da b2b-sales?  (só para provar que a guarda enxerga as linhas do banco)
        act = await oa.find_owner_activity(db, 154, "b2b-sales", 3 * 86400)
        print("atividade do dono no contato 154 (3 dias):", act)
asyncio.run(run())
print("guarda do dono carregada")
PY
echo "OK"
echo "SUCESSO: loja, B2B e Azusa agora ficam calados enquanto você está ativo na conversa; alertas ao dono saem por outra linha se a da loja cair. Para desfazer: bash rollback_ownerguard.sh"
