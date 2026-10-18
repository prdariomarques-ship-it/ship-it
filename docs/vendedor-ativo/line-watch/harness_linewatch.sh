#!/bin/bash
# Testa a LÓGICA dos scripts do vigia com um "docker" de mentira, usando os arquivos REAIS do repositório antes da mudança.
# Uso (de dentro do repositório, com a mudança commitada):  BASE=<commit anterior> bash docs/vendedor-ativo/line-watch/harness_linewatch.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$HERE"
BASE="${BASE:-HEAD~1}"; PH=5511912345678
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/dir $T/fake/root/app/utils $T/fake/root/app/services $T/fake/root/app/jobs
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  ( cd $ROOT; git show $BASE:backend/utils/config.py > $T/fake/root/app/utils/config.py; git show $BASE:backend/main.py > $T/fake/root/app/main.py )
  cp aplicar_linewatch.py aplicar_na_vps_linewatch.sh rollback_linewatch.sh line_watch.py line_watch_job.py $T/dir/
}
state() { cat $T/fake/root/app/utils/config.py $T/fake/root/app/main.py | sha256sum | cut -c1-12; }
newfiles() { ls $T/fake/root/app/services/line_watch.py $T/fake/root/app/jobs/line_watch_job.py 2>/dev/null | wc -l; }
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 LW_PHONE="$PH" "$@"; cd $T/dir; bash aplicar_na_vps_linewatch.sh < /dev/null > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
runrb() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 PY_REMOVES_JOBS=1; cd $T/dir; bash rollback_linewatch.sh < /dev/null > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt ); }
report() {  # nome ; exit ; antes|mudou ; arquivos novos esperados ; reinícios esperados
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(state); nf=$(newfiles); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true); rs=${rs:-0}; tmp=$(find $T/fake/root/app -name '*.lw_new' | wc -l)
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$nf" = "$4" ] && [ "$rs" = "$5" ] && [ "$tmp" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos=$3 novos=$nf reinicios=$rs temporarios=$tmp"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(state); runapply;                                                  report "1 sucesso" 0 mudou 2 1
grep -q 'line_watch_enabled: bool = True' $T/fake/root/app/utils/config.py && grep -q "line_watch_alert_phone: str = \"$PH\"" $T/fake/root/app/utils/config.py && grep -q 'Dário Marques Neto' $T/fake/root/app/utils/config.py && grep -q '^import jobs.line_watch_job' $T/fake/root/app/main.py && echo "[OK] 1b config (ligado, telefone, 4 linhas) e import no main" || echo "[FALHOU] 1b"
grep -q "$PH" $T/out.txt && echo "[FALHOU] 1c telefone completo apareceu na saída" || echo "[OK] 1c telefone completo não aparece na saída (só os 4 últimos dígitos)"
new_case; ORIG=$(state); ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 FAKE_ENV_PHONE=$PH; unset LW_PHONE; cd $T/dir; bash aplicar_na_vps_linewatch.sh < /dev/null > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); report "2 telefone vem do ambiente do container" 0 mudou 2 1
new_case; ORIG=$(state); runapply LW_PHONE=123;                                    report "3 telefone inválido -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "4 verificação funcional falha -> restaura e reinicia" 1 antes 0 2
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply FAIL_PY_N=2; report "5 semeadura falha -> restaura e reinicia" 1 antes 0 2
new_case; sed -i '/^import observation.scheduler/d' $T/fake/root/app/main.py; ORIG=$(state); runapply; report "6 main sem a âncora -> aborta sem tocar" 1 antes 0 0
new_case; sed -i 's/^    stt_background_enabled: bool = False$/    stt_background_enabled: bool = True/' $T/fake/root/app/utils/config.py; ORIG=$(state); runapply; report "7 config sem a âncora -> aborta sem tocar" 1 antes 0 0
new_case; echo "# velho" > $T/fake/root/app/services/line_watch.py; ORIG=$(state); runapply; nf=$(newfiles); [ "$nf" = 1 ] && grep -q 'exit=1' $T/out.txt && [ "$(state)" = "$ORIG" ] && echo "[OK] 8 módulo já existe no container -> aborta sem tocar" || echo "[FALHOU] 8"
new_case; echo "# adulterado" >> $T/dir/line_watch_job.py; ORIG=$(state); runapply; report "9 arquivo da pasta adulterado (hash) -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); runapply FAIL_SWAP=1;                                      report "10 troca falha -> restaura e reinicia" 1 antes 0 1
new_case; ORIG=$(state); touch $T/fake/unhealthy; runapply;                         report "11 container sem health -> aborta sem tocar" 1 antes 0 0
new_case; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && [ "$(newfiles)" = 0 ] && grep -q 'exit=0' $T/out2.txt && grep -q 'limpeza de jobs' $T/fake/events && echo "[OK] 12 rollback depois do sucesso: arquivos originais, módulos removidos, jobs apagados" || { echo "[FALHOU] 12"; tail -4 $T/out2.txt; }
new_case; ORIG=$(state); runapply; O1=$(sha256sum $T/dir/main.py.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/main.py.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 13 repetir o apply: aborta e o .orig guardado não é sobrescrito" || echo "[FALHOU] 13"
runrb; [ "$(state)" = "$ORIG" ] && echo "[OK] 13b rollback ainda funciona depois da repetição" || echo "[FALHOU] 13b"
