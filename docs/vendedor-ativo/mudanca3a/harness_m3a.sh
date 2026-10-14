#!/bin/bash
# Testa a LOGICA dos scripts da Mudança 3 com um "docker" de mentira (fakedocker.sh). Uso: bash harness_m3a.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
PA=agents/prompts/darius_twin.md; PB=agents/prompts/twin_conversation.md
mk_manual() { { echo "# Manual"; echo "Responder em primeira pessoa como se fosse eu mesmo, Dário."
  echo 'Nunca dizer espontaneamente "sou sou um assistente", x' > /dev/null
  echo 'Nunca dizer espontaneamente "sou um assistente", "sou um bot", "sou uma IA" ou usar qualquer linguagem que quebre a naturalidade da conversa.'
  echo '"Sou o Dário, seguindo com vc aqui sobre [o assunto já em conversa]"'; } > "$1"; }
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/fake/root/app/agents/prompts $T/dir
  sed 's/messaging.py.m2a_new/twin_conversation.md.m3a_new/; s/m2a_new/m3a_new/' fakedocker.sh > $T/bin/docker; chmod +x $T/bin/docker
  mk_manual $T/fake/root/app/$PA; printf '# Conversa\nregra 1\n' > $T/fake/root/app/$PB
  cp aplicar_m3a.py aplicar_na_vps_m3a.sh rollback_m3a.sh $T/dir/
}
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH "$@"; cd $T/dir; bash aplicar_na_vps_m3a.sh > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
hashes() { echo "$(sha256sum $T/fake/root/app/$PA | cut -c1-12) $(sha256sum $T/fake/root/app/$PB | cut -c1-12)"; }
report() {  # nome ; exit ; "antes"|"mudou"
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(hashes)
  left=$(ls $T/fake/root/app/agents/prompts | grep -c 'm3a_new\|m3a_bak\|m3a_rb' || true)
  tmp=$(ls $T/fake/root/app/agents/prompts | grep -c 'm3a_new' || true)
  restarts=$(grep -c restarted $T/fake/events 2>/dev/null || true)
  [ "$3" = antes ] && want="$ORIG" || want=""
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$tmp" = 0 ] && [ "${restarts:-0}" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos=$3 temporarios=$tmp reinicios=${restarts:-0}"
  [ "$ok" = FALHOU ] && tail -8 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(hashes); runapply;                                      report "1 sucesso" 0 mudou
grep -q "Aqui é o Twin, assistente do Dário" $T/fake/root/app/$PA && grep -q "Fatos autorizados" $T/fake/root/app/$PB && echo "[OK] 1b conteudo novo nos dois arquivos" || echo "[FALHOU] 1b conteudo"
new_case; ORIG=$(hashes); touch $T/fake/smoke_fail; runapply;            report "2 verificacao funcional falha -> restaura" 1 antes
new_case; echo "outra linha" >> $T/fake/root/app/$PA; ORIG=$(hashes); runapply
sed -i 's/Responder em primeira pessoa como se fosse eu mesmo, Dário.//' $T/fake/root/app/$PA; ORIG=$(hashes); runapply; report "3 trecho do manual ausente -> aborta sem tocar" 1 antes
new_case; echo '<!-- FICHA-M3A:INICIO -->' >> $T/fake/root/app/$PB; ORIG=$(hashes); runapply; report "4 bloco ja existe -> aborta sem tocar" 1 antes
new_case; ORIG=$(hashes); runapply CORRUPT_CP=1;                         report "5 copia temporaria corrompida -> aborta sem tocar" 1 antes
new_case; ORIG=$(hashes); runapply FAIL_SECOND_MV=1;                     report "6 segundo mv falha -> restaura" 1 antes
new_case; ORIG=$(hashes); touch $T/fake/unhealthy; runapply;             report "7 container sem health -> aborta sem tocar" 1 antes
new_case; ORIG=$(hashes); runapply; ( export FAKE=$T/fake PATH=$T/bin:$PATH; cd $T/dir; bash rollback_m3a.sh > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt )
[ "$(hashes)" = "$ORIG" ] && grep -q 'exit=0' $T/out2.txt && echo "[OK] 8 rollback depois do sucesso: $(grep -v '^exit' $T/out2.txt | tail -1)" || { echo "[FALHOU] 8 rollback"; tail -5 $T/out2.txt; }
