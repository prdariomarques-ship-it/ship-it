#!/bin/bash
# Testa a LÓGICA dos scripts com um "docker" de mentira, usando os arquivos REAIS do repositório antes da mudança (git show HEAD~N).
# Uso (de dentro do repositório, com a mudança já commitada):  BASE=<commit anterior> bash docs/vendedor-ativo/b2b-audio/harness_b2b.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$HERE"
BASE="${BASE:-HEAD~1}"
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/dir $T/fake/root/app/utils $T/fake/root/app/providers/whatsapp/evolution
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  ( cd $ROOT; git show $BASE:backend/utils/config.py > $T/fake/root/app/utils/config.py; git show $BASE:backend/providers/whatsapp/evolution/provider.py > $T/fake/root/app/providers/whatsapp/evolution/provider.py )
  cp aplicar_b2b.py aplicar_na_vps_b2b.sh rollback_b2b.sh $T/dir/
}
state() { cat $T/fake/root/app/utils/config.py $T/fake/root/app/providers/whatsapp/evolution/provider.py | sha256sum | cut -c1-12; }
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2 "$@"; cd $T/dir; bash aplicar_na_vps_b2b.sh > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
runrb() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2; cd $T/dir; bash rollback_b2b.sh > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt ); }
report() {
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(state); tmp=$(find $T/fake/root/app -name '*.b2b_new' | wc -l); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true); rs=${rs:-0}
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$tmp" = 0 ] && [ "$rs" = "$4" ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos=$3 temporarios=$tmp reinicios=$rs"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(state); runapply;                                      report "1 sucesso" 0 mudou 1
grep -q 'evolution_media_extra_instances: str = "b2b-sales"' $T/fake/root/app/utils/config.py && grep -q '| extra' $T/fake/root/app/providers/whatsapp/evolution/provider.py && echo "[OK] 1b padrão b2b-sales e checagem nova presentes" || echo "[FALHOU] 1b"
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "2 verificação funcional falha -> restaura e reinicia" 1 antes 2
new_case; sed -i 's/        if instance and instance not in {self._instance, self._personal_instance}:/        if instance and instance not in {self._instance}:/' $T/fake/root/app/providers/whatsapp/evolution/provider.py; ORIG=$(state); runapply; report "3 provider divergente (âncora some) -> aborta sem tocar" 1 antes 0
new_case; sed -i 's/^    stt_background_enabled: bool = False$/    stt_background_enabled: bool = True/' $T/fake/root/app/utils/config.py; ORIG=$(state); runapply; report "4 config divergente (âncora some) -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply FAIL_SWAP=1;                          report "6 troca falha -> restaura e reinicia" 1 antes 1
new_case; ORIG=$(state); touch $T/fake/unhealthy; runapply;             report "7 container sem health -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && grep -q 'exit=0' $T/out2.txt && echo "[OK] 8 rollback depois do sucesso: arquivos iguais aos originais" || { echo "[FALHOU] 8"; tail -4 $T/out2.txt; }
new_case; ORIG=$(state); runapply; O1=$(sha256sum $T/dir/provider.py.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/provider.py.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 9 repetir o apply: aborta e o .orig guardado não é sobrescrito" || echo "[FALHOU] 9"
runrb; [ "$(state)" = "$ORIG" ] && echo "[OK] 9b rollback ainda funciona depois da repetição" || echo "[FALHOU] 9b"
