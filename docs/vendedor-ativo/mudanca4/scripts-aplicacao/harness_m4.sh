#!/bin/bash
# Testa a LOGICA dos scripts da Mudança 4 com um "docker" de mentira (fakedocker.sh). Uso: bash harness_m4.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
PROD="$HERE/../../mudanca2a/bases-producao"
W="$(mktemp -d)"; cp "$PROD/handlers.py" "$W/handlers.py.novo"; cp "$PROD/messaging.py" "$W/messaging.py.novo"
(cd "$W" && python3 "$HERE/../../mudanca2a/aplicar_m2a.py" > /dev/null && cp handlers.py.novo handlers_2a.py && python3 "$HERE/../aplicar_m4.py" > /dev/null)
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/fake/root/app/jobs $T/dir
  cp fakedocker.sh $T/bin/docker; cp $W/handlers_2a.py $T/fake/root/app/jobs/handlers.py
  cp $W/handlers_2a.py $T/dir/handlers.py.orig; cp $W/handlers.py.novo $T/dir/handlers.py.novo
  printf '# familia\n14  # Elaine\n' > $T/dir/lista_silenciosos.txt
  cp aplicar_na_vps_m4.sh rollback_na_vps_m4.sh $T/dir/
  sed -i 's/seq 1 30/seq 1 2/; s/sleep 5/sleep 0/' $T/dir/*.sh
}
report() {  # nome ; esperado_exit ; esperado_hash(16) ; esperado_reinicios ; lista_existe(0/1)
  h=$(sha256sum $T/fake/root/app/jobs/handlers.py | cut -c1-16)
  r=$(grep -c restarted $T/fake/events 2>/dev/null || true); r=${r:-0}
  left=$(ls $T/fake/root/app/jobs $T/fake/root/app | grep -c 'm4_new' || true)
  lista=0; [ -e $T/fake/root/app/twin_silent_contacts.txt ] && lista=1
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1)
  ok=OK; [ "$ex" = "exit=$2" ] && [ "$h" = "$3" ] && [ "$r" = "$4" ] && [ "$left" = 0 ] && [ "$lista" = "$5" ] || ok=FALHOU
  echo "[$ok] $1: $ex handlers=$h reinicios=$r temporarios=$left lista=$lista"
  [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH "$@"; cd $T/dir; bash aplicar_na_vps_m4.sh > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
NEWH=$(sha256sum $W/handlers.py.novo | cut -c1-16); OLDH=$(sha256sum $W/handlers_2a.py | cut -c1-16)

new_case; runapply;                                         report "1 sucesso" 0 $NEWH 1 1
new_case; touch $T/fake/smoke_fail; runapply;               report "2 verificacao funcional falha -> reverte" 1 $OLDH 2 1
new_case; echo "# alterado" >> $T/fake/root/app/jobs/handlers.py; ALT=$(sha256sum $T/fake/root/app/jobs/handlers.py | cut -c1-16); runapply; report "3 container diferente do esperado -> aborta sem tocar" 1 $ALT 0 0
new_case; runapply CORRUPT_CP=1;                            report "4 copia temporaria corrompida -> aborta sem tocar" 1 $OLDH 0 0
new_case; echo "999" > $T/fake/root/app/twin_silent_contacts.txt; runapply; report "5 lista ja existe -> aborta sem tocar" 1 $OLDH 0 1
new_case; touch $T/fake/unhealthy_after_restart; runapply;  report "6 nao fica healthy -> reverte" 1 $OLDH 2 1
new_case; echo "Traceback (most recent call last)" > $T/fake/logs; runapply; report "7 traceback nos logs -> reverte" 1 $OLDH 2 1
new_case; rm $T/dir/lista_silenciosos.txt; runapply;        report "8 falta a lista -> aborta sem tocar" 1 $OLDH 0 0
new_case; runapply; ( export FAKE=$T/fake PATH=$T/bin:$PATH; cd $T/dir; bash rollback_na_vps_m4.sh > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt )
h=$(sha256sum $T/fake/root/app/jobs/handlers.py | cut -c1-16); r=$(grep -c restarted $T/fake/events)
echo "[$([ "$h" = $OLDH ] && [ "$r" = 2 ] && grep -q 'exit=0' $T/out2.txt && echo OK || echo FALHOU)] 9 rollback depois do sucesso: $(grep -v '^exit' $T/out2.txt | tail -1 | cut -c1-70) reinicios=$r"
