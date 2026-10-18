#!/bin/bash
# Testa a LÓGICA dos scripts com docker de mentira, usando o handlers.py REAL do repositório antes da mudança e os dois módulos do vigia já aplicado.
# Uso (de dentro do repositório):  BASE=<commit anterior ao roteamento> bash docs/vendedor-ativo/alert-routing/harness_roteamento.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$HERE"
BASE="${BASE:-HEAD~1}"
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/dir $T/fake/root/app/services $T/fake/root/app/jobs
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  ( cd $ROOT; git show $BASE:backend/jobs/handlers.py > $T/fake/root/app/jobs/handlers.py )
  cp $ROOT/docs/vendedor-ativo/line-watch/line_watch.py $T/fake/root/app/services/line_watch.py
  cp $ROOT/docs/vendedor-ativo/line-watch/line_watch_job.py $T/fake/root/app/jobs/line_watch_job.py
  cp aplicar_roteamento.py aplicar_na_vps_roteamento.sh rollback_roteamento.sh line_watch.py line_watch_job.py $T/dir/
}
state() { cat $T/fake/root/app/jobs/handlers.py $T/fake/root/app/services/line_watch.py $T/fake/root/app/jobs/line_watch_job.py | sha256sum | cut -c1-12; }
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 "$@"; cd $T/dir; bash aplicar_na_vps_roteamento.sh < /dev/null > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
runrb() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2; cd $T/dir; bash rollback_roteamento.sh < /dev/null > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt ); }
report() {
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(state); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true); rs=${rs:-0}; tmp=$(find $T/fake/root/app -name '*.rt_new' | wc -l)
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$rs" = "$4" ] && [ "$tmp" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos=$3 reinicios=$rs temporarios=$tmp"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(state); runapply;                                                  report "1 sucesso" 0 mudou 1
grep -q 'line_watch.alert_instance' $T/fake/root/app/jobs/handlers.py && grep -q 'def alert_instance' $T/fake/root/app/services/line_watch.py && echo "[OK] 1b handlers e módulo novos no container" || echo "[FALHOU] 1b"
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "2 verificação funcional falha -> restaura e reinicia" 1 antes 2
new_case; sed -i "s/^    alert_dedup_key = payload.get('_twin_alert_dedup_key')$/    alert_dedup_key = None/" $T/fake/root/app/jobs/handlers.py; ORIG=$(state); runapply; report "3 handlers sem a âncora -> aborta sem tocar" 1 antes 0
new_case; echo "# editado" >> $T/fake/root/app/services/line_watch.py; ORIG=$(state); runapply; report "4 line_watch do container diferente do vigia aplicado -> aborta sem tocar" 1 antes 0
new_case; echo "# adulterado" >> $T/dir/line_watch_job.py; ORIG=$(state); runapply; report "5 arquivo da pasta adulterado -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply FAIL_SWAP=1;                                      report "6 troca falha -> restaura e reinicia" 1 antes 1
new_case; ORIG=$(state); touch $T/fake/unhealthy; runapply;                         report "7 container sem health -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && grep -q 'exit=0' $T/out2.txt && echo "[OK] 8 rollback depois do sucesso: 3 arquivos originais" || { echo "[FALHOU] 8"; tail -4 $T/out2.txt; }
new_case; ORIG=$(state); runapply; O1=$(sha256sum $T/dir/handlers.py.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/handlers.py.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 9 repetir o apply: aborta e o .orig guardado não é sobrescrito" || echo "[FALHOU] 9"
runrb; [ "$(state)" = "$ORIG" ] && echo "[OK] 9b rollback ainda funciona depois da repetição" || echo "[FALHOU] 9b"
