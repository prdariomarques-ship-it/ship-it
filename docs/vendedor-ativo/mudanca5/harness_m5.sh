#!/bin/bash
# Testa a LOGICA dos scripts da Mudança 5 com um "docker" de mentira (fakedocker.sh). Uso: bash harness_m5.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
PB=agents/prompts/twin_conversation.md
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/fake/root/app/agents/prompts $T/dir
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  printf '# Conversa\nregra 1\n\n<!-- FICHA-M3A:INICIO -->\n## Fatos autorizados sobre o Dário\n<!-- FICHA-M3A:FIM -->\n' > $T/fake/root/app/$PB
  cp aplicar_m5.py aplicar_na_vps_m5.sh rollback_m5.sh $T/dir/
  sed -i "s/^B_ORIG_ESPERADO=[0-9a-f]*/B_ORIG_ESPERADO=$(sha256sum $T/fake/root/app/$PB | cut -d' ' -f1)/" $T/dir/aplicar_na_vps_m5.sh
}
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH "$@"; cd $T/dir; bash aplicar_na_vps_m5.sh > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
h() { sha256sum $T/fake/root/app/$PB | cut -c1-12; }
report() {  # nome ; exit ; antes|mudou
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(h); tmp=$(ls $T/fake/root/app/agents/prompts | grep -c 'm5_new' || true); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true)
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$tmp" = 0 ] && [ "${rs:-0}" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivo=$3 temporarios=$tmp reinicios=${rs:-0}"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(h); runapply;                                   report "1 sucesso" 0 mudou
grep -q "Compromissos em nome do Dário" $T/fake/root/app/$PB && grep -q "Fatos autorizados" $T/fake/root/app/$PB && echo "[OK] 1b bloco novo e bloco da M3 presentes" || echo "[FALHOU] 1b"
new_case; ORIG=$(h); touch $T/fake/smoke_fail; runapply;         report "2 verificacao funcional falha -> restaura" 1 antes
new_case; echo "editado fora" >> $T/fake/root/app/$PB; ORIG=$(h); runapply; report "3 texto diferente da Mudanca 3 -> aborta sem tocar" 1 antes
new_case; sed -i 's#^B_ORIG_ESPERADO=.*#B_ORIG_ESPERADO=X#' $T/dir/aplicar_na_vps_m5.sh; ORIG=$(h); runapply; report "3b hash esperado errado -> aborta sem tocar" 1 antes
new_case; printf '<!-- FICHA-M5:INICIO -->\n' >> $T/fake/root/app/$PB; ORIG=$(h); sed -i "s/^B_ORIG_ESPERADO=[0-9a-f]*/B_ORIG_ESPERADO=$(sha256sum $T/fake/root/app/$PB | cut -d' ' -f1)/" $T/dir/aplicar_na_vps_m5.sh; runapply; report "4 bloco ja existe -> aborta sem tocar" 1 antes
new_case; ORIG=$(h); runapply CORRUPT_CP=1;                      report "5 copia temporaria corrompida -> aborta sem tocar" 1 antes
new_case; ORIG=$(h); runapply FAIL_SECOND_MV=1;                  report "6 troca falha -> restaura" 1 antes
new_case; ORIG=$(h); touch $T/fake/unhealthy; runapply;          report "7 container sem health -> aborta sem tocar" 1 antes
new_case; ORIG=$(h); runapply; ( export FAKE=$T/fake PATH=$T/bin:$PATH; cd $T/dir; bash rollback_m5.sh > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt )
[ "$(h)" = "$ORIG" ] && grep -q 'exit=0' $T/out2.txt && echo "[OK] 8 rollback depois do sucesso: $(grep -v '^exit' $T/out2.txt | tail -1)" || { echo "[FALHOU] 8 rollback"; tail -4 $T/out2.txt; }
# 9. repetir o apply depois do sucesso aborta e NAO sobrescreve o .orig guardado (defeito visto na VPS em 15/10)
new_case; ORIG=$(h); runapply; O1=$(sha256sum $T/dir/twin_conversation.md.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/twin_conversation.md.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 9 repetir o apply depois do sucesso: aborta e o .orig guardado continua o mesmo" || echo "[FALHOU] 9 .orig sobrescrito ou nao abortou"
( export FAKE=$T/fake PATH=$T/bin:$PATH; cd $T/dir; bash rollback_m5.sh > $T/out3.txt 2>&1 ); [ "$(h)" = "$ORIG" ] && echo "[OK] 9b rollback ainda funciona depois da repeticao" || { echo "[FALHOU] 9b"; tail -3 $T/out3.txt; }
