#!/bin/bash
# Alerta ao dono por outra linha quando a da loja cai. Uso:  bash aplicar_na_vps_roteamento.sh   (na pasta com aplicar_roteamento.py, line_watch.py, line_watch_job.py)
# Atualiza line_watch.py e line_watch_job.py (versões do vigia já aplicado) e faz UMA edição ancorada no handlers.py. REINICIA o backend (segundos).
# NÃO envia mensagens. Qualquer falha devolve os 3 arquivos e reinicia de novo.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
SVC=/app/services/line_watch.py; JOB=/app/jobs/line_watch_job.py; HND=/app/jobs/handlers.py
OLD_SVC=f6b6d5e1a6d0c8bea50293d5b24530ccb5edcd4861b1dce0c618d4d5ccb1a79c
OLD_JOB=e9ccfa2659bc350d3f7e24f80b61ea782b741f70024daeeec95bafaed121674e
NEW_SVC=ba87dd02cdb69feaed5fd3978e7c2def1624ccd1f2aec044b26be637690b2f50
NEW_JOB=21ac90687208fec800ea9ba9135bf908a940a57d12a11e4eb5f24e8cc1e5e07a
ESPERA_HEALTH=${ESPERA_HEALTH:-90}

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { local i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
trap 'docker exec "$BK" rm -f "$SVC.rt_new" "$JOB.rt_new" "$HND.rt_new" >/dev/null 2>&1 || true' EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  docker cp line_watch.py.orig "$BK:$SVC" || echo "ATENÇÃO: falha ao copiar line_watch.py"
  docker cp line_watch_job.py.orig "$BK:$JOB" || echo "ATENÇÃO: falha ao copiar line_watch_job.py"
  docker cp handlers.py.orig "$BK:$HND" || echo "ATENÇÃO: falha ao copiar handlers.py"
  docker restart "$BK" >/dev/null || echo "ATENÇÃO: falha ao reiniciar"
  wait_healthy && echo "backend healthy de novo" || echo "ATENÇÃO: backend não ficou healthy; rode rollback_roteamento.sh e olhe docker logs"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. confere os arquivos desta pasta e lê os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_roteamento.py ] && [ -s line_watch.py ] && [ -s line_watch_job.py ] || die "faltam arquivos nesta pasta"
expect "line_watch.py desta pasta" "$(sha_file line_watch.py)" "$NEW_SVC"
expect "line_watch_job.py desta pasta" "$(sha_file line_watch_job.py)" "$NEW_JOB"
for f in line_watch.py:$SVC line_watch_job.py:$JOB handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  docker cp "$BK:$p" "$n.lido"; [ -s "$n.lido" ] || die "não consegui ler $p"
  expect "$n (cópia fiel)" "$(sha_live $p)" "$(sha_file $n.lido)"
done
expect "line_watch.py do container é a versão do vigia aplicado" "$(sha_file line_watch.py.lido)" "$OLD_SVC"
expect "line_watch_job.py do container é a versão do vigia aplicado" "$(sha_file line_watch_job.py.lido)" "$OLD_JOB"
python3 aplicar_roteamento.py . || die "o aplicar_roteamento.py recusou (nada foi gravado no container)"
for n in line_watch.py line_watch_job.py handlers.py; do mv "$n.lido" "$n.orig"; printf '%s  %s\n' "$(sha_file $n.orig)" "$n" >> hashes_antes_roteamento.tmp; done
mv hashes_antes_roteamento.tmp hashes_antes_roteamento.txt
echo "OK (originais guardados como *.orig)"

echo "== 2. copia para nomes temporários e confere (o código em uso não muda)"
docker cp line_watch.py "$BK:$SVC.rt_new"; docker cp line_watch_job.py "$BK:$JOB.rt_new"; docker cp handlers.py.novo "$BK:$HND.rt_new"
expect "line_watch temporário" "$(sha_live $SVC.rt_new)" "$NEW_SVC"
expect "line_watch_job temporário" "$(sha_live $JOB.rt_new)" "$NEW_JOB"
expect "handlers temporário" "$(sha_live $HND.rt_new)" "$(sha_file handlers.py.novo)"
echo "OK"

echo "== 3. troca (cópias de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $SVC $SVC.rt_bak; cp -p $JOB $JOB.rt_bak; cp -p $HND $HND.rt_bak; mv $SVC.rt_new $SVC; mv $JOB.rt_new $JOB; mv $HND.rt_new $HND"; then back_out "a troca falhou"; fi
expect "handlers final" "$(sha_live $HND)" "$(sha_file handlers.py.novo)"
echo "OK"

echo "== 4. reinicia o backend e espera ficar healthy"
docker restart "$BK" >/dev/null || back_out "o restart falhou"
wait_healthy || back_out "o backend não ficou healthy em ${ESPERA_HEALTH}s"
echo "OK"

echo "== 5. verificação funcional (sem rede e sem enviar mensagem)"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import jobs.handlers  # noqa: F401  (importa sem erro)
from services import line_watch
from utils.config import get_settings

s = get_settings()
assert line_watch.alert_instance(s) is None, "sem leitura recente o padrão tem de ser mantido"
line_watch.record_states({s.evolution_instance: "connecting", "b2b-sales": "open"})
assert line_watch.alert_instance(s) == "b2b-sales", line_watch.alert_instance(s)
line_watch.record_states({s.evolution_instance: "open", "b2b-sales": "open"})
assert line_watch.alert_instance(s) is None
line_watch.line_watch_state.reset()
print("roteamento de alertas OK (loja fora -> b2b-sales; loja no ar -> padrão)")
PY
echo "OK"
echo "SUCESSO: alertas ao dono agora saem por outra linha quando a da loja está fora do ar. Para desfazer: bash rollback_roteamento.sh"
