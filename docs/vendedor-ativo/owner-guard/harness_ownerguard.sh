#!/bin/bash
# Testa a LÓGICA dos scripts com docker de mentira, usando o texto REAL de produção (prod_fixture_handlers.py) e o vigia já aplicado.
# Uso (de dentro do repositório):  bash docs/vendedor-ativo/owner-guard/harness_ownerguard.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$HERE"
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/dir $T/fake/root/app/services $T/fake/root/app/jobs
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  cp prod_fixture_handlers.py $T/fake/root/app/jobs/handlers.py
  cp $ROOT/docs/vendedor-ativo/line-watch/line_watch.py $T/fake/root/app/services/line_watch.py
  cp $ROOT/docs/vendedor-ativo/line-watch/line_watch_job.py $T/fake/root/app/jobs/line_watch_job.py
  cp aplicar_owner_guard.py aplicar_na_vps_ownerguard.sh rollback_ownerguard.sh owner_activity.py line_watch.py line_watch_job.py $T/dir/
}
state() { cat $T/fake/root/app/jobs/handlers.py $T/fake/root/app/services/line_watch.py $T/fake/root/app/jobs/line_watch_job.py | sha256sum | cut -c1-12; }
extras() { ls $T/fake/root/app/services/owner_activity.py $T/fake/root/app/owner_activity_windows.txt 2>/dev/null | wc -l; }
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 "$@"; cd $T/dir; bash aplicar_na_vps_ownerguard.sh < /dev/null > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
runrb() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2; cd $T/dir; bash rollback_ownerguard.sh < /dev/null > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt ); }
report() {  # nome ; exit ; antes|mudou ; extras esperados ; reinícios
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(state); xs=$(extras); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true); rs=${rs:-0}; tmp=$(find $T/fake/root/app -name '*.og_new' | wc -l)
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$xs" = "$4" ] && [ "$rs" = "$5" ] && [ "$tmp" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos=$3 extras=$xs reinicios=$rs temporarios=$tmp"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(state); runapply;                                                  report "1 sucesso" 0 mudou 2 1
grep -q 'default=360' $T/fake/root/app/owner_activity_windows.txt && grep -q '_oa.send_guard' $T/fake/root/app/jobs/handlers.py && echo "[OK] 1b janelas criadas e handlers editados" || echo "[FALHOU] 1b"
new_case; printf 'b2b=60\n' > $T/fake/root/app/owner_activity_windows.txt; ORIG=$(state); runapply
[ "$(cat $T/fake/root/app/owner_activity_windows.txt)" = "b2b=60" ] && grep -q 'exit=0' $T/out.txt && echo "[OK] 2 arquivo de janelas já existente NÃO é sobrescrito" || echo "[FALHOU] 2"
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "3 verificação funcional falha -> restaura, remove módulo e janelas, reinicia" 1 antes 0 2
new_case; sed -i 's/^        from services.store_aftercare import is_stop_request, stop_followups$/        pass/' $T/fake/root/app/jobs/handlers.py; sed -i 's/^    reply_phone = contact.phone$/    reply_phone = contact.phone  # alterado/' $T/fake/root/app/jobs/handlers.py; ORIG=$(state); runapply; report "4 handlers diferente (âncora some) -> aborta sem tocar" 1 antes 0 0
new_case; echo "# editado" >> $T/fake/root/app/services/line_watch.py; ORIG=$(state); runapply; report "5 line_watch do container diferente do vigia aplicado -> aborta sem tocar" 1 antes 0 0
new_case; echo "# adulterado" >> $T/dir/owner_activity.py; ORIG=$(state); runapply; report "6 arquivo da pasta adulterado -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); runapply FAIL_SWAP=1;                                      report "7 troca falha -> restaura e reinicia" 1 antes 0 1
new_case; ORIG=$(state); touch $T/fake/unhealthy; runapply;                         report "8 container sem health -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && [ "$(extras)" = 0 ] && grep -q 'exit=0' $T/out2.txt && echo "[OK] 9 rollback depois do sucesso: 3 arquivos originais, módulo e janelas removidos" || { echo "[FALHOU] 9"; tail -4 $T/out2.txt; }
new_case; ORIG=$(state); runapply; O1=$(sha256sum $T/dir/handlers.py.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/handlers.py.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 10 repetir o apply: aborta e o .orig guardado não é sobrescrito" || echo "[FALHOU] 10"
runrb; [ "$(state)" = "$ORIG" ] && echo "[OK] 10b rollback ainda funciona depois da repetição" || echo "[FALHOU] 10b"
