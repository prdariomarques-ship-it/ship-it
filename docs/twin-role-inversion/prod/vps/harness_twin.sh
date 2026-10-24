#!/bin/bash
# Testa a LOGICA dos scripts com docker de mentira, sobre o texto REAL de producao (../originais). Nao toca em nenhuma VPS.
# Uso (de dentro do repositorio):  bash docs/twin-role-inversion/prod/vps/harness_twin.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../../.." && pwd)"; PROD="$HERE/.."; OG="$ROOT/docs/vendedor-ativo/owner-guard"; cd "$HERE"
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/dir $T/fake/root/app/agents $T/fake/root/app/jobs $T/fake/root/app/orchestrator
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  cp $PROD/originais/darius_twin.py $T/fake/root/app/agents/darius_twin.py; cp $PROD/originais/handlers.py $T/fake/root/app/jobs/handlers.py
  cp aplicar_na_vps_twin.sh rollback_twin.sh $PROD/aplicar_twin_roles.py $T/dir/
  cp $ROOT/backend/agents/darius_twin_roles.py $ROOT/backend/agents/darius_twin_actions.py $ROOT/backend/orchestrator/twin_silence.py $T/dir/
  (cd $T/dir && sha256sum aplicar_twin_roles.py darius_twin_roles.py darius_twin_actions.py twin_silence.py > SHA256SUMS)
}
state() { cat $T/fake/root/app/agents/darius_twin.py $T/fake/root/app/jobs/handlers.py | sha256sum | cut -c1-12; }
extras() { ls $T/fake/root/app/agents/darius_twin_roles.py $T/fake/root/app/agents/darius_twin_actions.py $T/fake/root/app/orchestrator/twin_silence.py 2>/dev/null | wc -l; }
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 "$@"; cd $T/dir; bash aplicar_na_vps_twin.sh < /dev/null > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
runrb() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2; cd $T/dir; bash rollback_twin.sh < /dev/null > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt ); }
report() {  # nome ; exit ; antes|mudou ; extras esperados ; reinicios
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(state); xs=$(extras); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true); rs=${rs:-0}; tmp=$(find $T/fake/root/app -name '*.tw_new' | wc -l)
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$xs" = "$4" ] && [ "$rs" = "$5" ] && [ "$tmp" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos=$3 extras=$xs reinicios=$rs temporarios=$tmp"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(state); runapply;                                                  report "1 sucesso" 0 mudou 3 1
grep -q 'twin_silence' $T/fake/root/app/jobs/handlers.py && grep -q 'blocked_action' $T/fake/root/app/jobs/handlers.py && grep -q 'build_twin_history' $T/fake/root/app/jobs/handlers.py && grep -q 'guard_role_inversion' $T/fake/root/app/agents/darius_twin.py && echo "[OK] 1b handlers e darius_twin editados" || echo "[FALHOU] 1b"
new_case; cp $PROD/originais/handlers.py $T/h.lido; mkdir -p $T/ogdir; cp $PROD/originais/handlers.py $T/ogdir/handlers.py.lido; python3 $OG/aplicar_owner_guard.py $T/ogdir > /dev/null; cp $T/ogdir/handlers.py.novo $T/fake/root/app/jobs/handlers.py; ORIG=$(state); runapply
report "2 handlers ja com owner-guard -> aplica por ancoras" 0 mudou 3 1; grep -q '_oa.send_guard' $T/fake/root/app/jobs/handlers.py && grep -q 'twin_silence' $T/fake/root/app/jobs/handlers.py && echo "[OK] 2b os dois patches coexistem" || echo "[FALHOU] 2b"
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "3 verificacao funcional falha -> restaura, remove modulos, reinicia" 1 antes 0 2
new_case; echo "# alterado" >> $T/fake/root/app/jobs/handlers.py; ORIG=$(state); runapply; report "4 handlers desconhecido (sem owner-guard) -> aborta sem tocar" 1 antes 0 0
new_case; echo "# alterado" >> $T/fake/root/app/agents/darius_twin.py; ORIG=$(state); runapply; report "5 darius_twin diferente do original -> aborta sem tocar" 1 antes 0 0
new_case; echo "# adulterado" >> $T/dir/twin_silence.py; ORIG=$(state); runapply; report "6 arquivo da pasta adulterado -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); runapply FAIL_SWAP=1;                                      report "7 troca falha -> restaura e reinicia" 1 antes 0 1
new_case; ORIG=$(state); touch $T/fake/unhealthy; runapply;                         report "8 container sem health -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && [ "$(extras)" = 0 ] && grep -q 'exit=0' $T/out2.txt && echo "[OK] 9 rollback depois do sucesso: 2 arquivos originais e 3 modulos removidos" || { echo "[FALHOU] 9"; tail -4 $T/out2.txt; }
new_case; ORIG=$(state); runapply; O1=$(sha256sum $T/dir/handlers.py.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/handlers.py.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 10 repetir o apply: aborta e o .orig guardado nao e sobrescrito" || echo "[FALHOU] 10"
runrb; [ "$(state)" = "$ORIG" ] && echo "[OK] 10b rollback ainda funciona depois da repeticao" || echo "[FALHOU] 10b"
new_case; mkdir -p $T/fake/root/app/orchestrator; echo "# ja existe" > $T/fake/root/app/orchestrator/twin_silence.py; ORIG=$(state); runapply; ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1)
[ "$ex" = "exit=1" ] && [ "$(state)" = "$ORIG" ] && echo "[OK] 11 modulo novo ja existe -> aborta sem tocar" || echo "[FALHOU] 11"
