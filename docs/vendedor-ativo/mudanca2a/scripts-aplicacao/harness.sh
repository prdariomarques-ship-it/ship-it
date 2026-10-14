#!/bin/bash
# Testa a LOGICA dos scripts de aplicacao/reversao com um "docker" de mentira (fakedocker.sh). Uso: bash harness.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
PROD="$HERE/../bases-producao"
W="$(mktemp -d)"; cp "$PROD/handlers.py" "$W/handlers.py.novo"; cp "$PROD/messaging.py" "$W/messaging.py.novo"
(cd "$W" && python3 "$HERE/../aplicar_m2a.py" > /dev/null)
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/fake/root/app/jobs $T/fake/root/app/services $T/dir
  cp fakedocker.sh $T/bin/docker
  cp $PROD/handlers.py $T/fake/root/app/jobs/handlers.py; cp $PROD/messaging.py $T/fake/root/app/services/messaging.py
  cp $PROD/handlers.py $T/dir/handlers.py.orig; cp $PROD/messaging.py $T/dir/messaging.py.orig
  cp $W/handlers.py.novo $T/dir/handlers.py.novo; cp $W/messaging.py.novo $T/dir/messaging.py.novo
  cp aplicar_na_vps.sh rollback_na_vps.sh $T/dir/
  sed -i 's/seq 1 30/seq 1 2/; s/sleep 5/sleep 0/' $T/dir/*.sh
}
report() {  # nome ; esperado_exit ; esperado_hash_handlers(16) ; esperado_reinicios
  h=$(sha256sum $T/fake/root/app/jobs/handlers.py | cut -c1-16); m=$(sha256sum $T/fake/root/app/services/messaging.py | cut -c1-16)
  r=$(grep -c restarted $T/fake/events 2>/dev/null || true); r=${r:-0}
  left=$(ls $T/fake/root/app/jobs $T/fake/root/app/services | grep -c 'm2a_new' || true)
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1)
  ok=OK; [ "$ex" = "exit=$2" ] && [ "$h" = "$3" ] && [ "$r" = "$4" ] && [ "$left" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex handlers=$h reinicios=$r temporarios_restantes=$left"
  [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH "$@"; cd $T/dir; bash aplicar_na_vps.sh > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
NEWH=bf3ff6b771721ace; OLDH=f7b077199defc5c9

new_case; runapply;                                           report "1 sucesso" 0 $NEWH 1
new_case; touch $T/fake/smoke_fail; runapply;                 report "2 verificacao funcional falha -> reverte" 1 $OLDH 2
new_case; echo "# alterado" >> $T/fake/root/app/jobs/handlers.py; ALT=$(sha256sum $T/fake/root/app/jobs/handlers.py | cut -c1-16); runapply; report "3 container diferente do esperado -> aborta sem tocar" 1 $ALT 0
new_case; CORRUPT=1 runapply CORRUPT_CP=1;                    report "4 copia temporaria corrompida -> aborta sem tocar" 1 $OLDH 0
new_case; runapply FAIL_SECOND_MV=1;                          report "5 segundo mv falha -> restaura, sem reinicio" 1 $OLDH 0
new_case; touch $T/fake/unhealthy_after_restart; runapply;    report "6 nao fica healthy -> reverte" 1 $OLDH 2
new_case; echo "Traceback (most recent call last)" > $T/fake/logs; runapply; report "7 traceback nos logs -> reverte" 1 $OLDH 2
new_case; runapply; ( export FAKE=$T/fake PATH=$T/bin:$PATH; cd $T/dir; bash rollback_na_vps.sh > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt )
h=$(sha256sum $T/fake/root/app/jobs/handlers.py | cut -c1-16); r=$(grep -c restarted $T/fake/events); echo "[$([ "$h" = $OLDH ] && [ "$r" = 2 ] && grep -q 'exit=0' $T/out2.txt && echo OK || echo FALHOU)] 8 rollback depois do sucesso: $(tail -1 $T/out2.txt) handlers=$h reinicios=$r"
