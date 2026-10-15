#!/bin/bash
# Testa a LOGICA de recuperar_patches.sh com um "docker" de mentira. Uso: bash harness_recuperacao.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"
mk_case() {  # $1 = o que ha no container: orig|novo|misto|outro
  T=$(mktemp -d); mkdir -p $T/bin $T/fake/root/app/jobs $T/fake/root/app/services $T/fake/root/app/agents/prompts $T/bkp
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  for n in handlers.py messaging.py darius_twin.md twin_conversation.md; do echo "NOVO-$n" > $T/bkp/$n; echo "ORIG-$n" > $T/o_$n; done
  echo "13" > $T/bkp/twin_silent_contacts.txt
  # hashes da tabela viram os dos arquivos de teste
  cp recuperar_patches.sh $T/rec.sh
  python3 - "$T" <<'PY'
import hashlib, sys, re
T = sys.argv[1]
s = open(f"{T}/rec.sh", encoding="utf-8").read()
for n, old_orig, old_new in [
 ("handlers.py","f7b077199defc5c969aa7f142c9e64b73775bdb730d74b1c38333b1618eaf0a8","9eb1e67c626efd3fbcb204e91cb794649be32b7e2e31b0af50d7b0bca64e15b1"),
 ("messaging.py","5b72aae2fcf268a39ba8c013ae60eb4329713c6d8d752198625e97401a31f1a0","42397ce3f0bd22d0a87966fd6ac1bf7f85f15eeb33f42889d3ed8ec20d53f4ca"),
 ("darius_twin.md","8639955aa1ae48c350ef2ae50715d61009ff4ec67062273eab36a3b1dee41e0b","2951896e864481da06615626bbd669015815228c8315171bcbfe2b38eae6c0ed"),
 ("twin_conversation.md","0ee24d0d8a72e6775cbbc189f74a6fa388fcc53d26edd487cd4a9d73ea607e19","ae8ea5208b22b4b062f90b90577c33a4ea7d7a7cb9389eb907168f98dfd7f6ed")]:
    h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    s = s.replace(old_orig, h(f"{T}/o_{n}")).replace(old_new, h(f"{T}/bkp/{n}"))
open(f"{T}/rec.sh", "w", encoding="utf-8").write(s.replace("seq 1 30", "seq 1 2").replace("sleep 5", "sleep 0"))
PY
  P=$T/fake/root/app
  put() { # arquivo, versao
    case $1 in handlers.py) d=$P/jobs;; messaging.py) d=$P/services;; *) d=$P/agents/prompts;; esac
    [ "$2" = orig ] && cp $T/o_$1 $d/$1 || cp $T/bkp/$1 $d/$1; }
  for n in handlers.py messaging.py darius_twin.md twin_conversation.md; do
    case $1 in orig) put $n orig;; novo) put $n novo;; misto) [ $n = handlers.py ] && put $n novo || put $n orig;; outro) echo "OUTRA IMAGEM" > $P/jobs/handlers.py; put messaging.py orig; put darius_twin.md orig; put twin_conversation.md orig;; esac
  done
}
run() { ( export FAKE=$T/fake PATH=$T/bin:$PATH "$@"; bash $T/rec.sh $T/bkp > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
estado() { P=$T/fake/root/app; n=0; for f in jobs/handlers.py services/messaging.py agents/prompts/darius_twin.md agents/prompts/twin_conversation.md; do grep -q NOVO $P/$f && n=$((n+1)); done; echo $n; }
rep() { ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); r=$(grep -c restarted $T/fake/events 2>/dev/null || true); tmp=$(ls -R $T/fake/root/app | grep -c 'rec_new' || true)
  ok=OK; [ "$ex" = "exit=$2" ] && [ "$(estado)" = "$3" ] && [ "${r:-0}" = "$4" ] && [ "$tmp" = 0 ] || ok=FALHOU
  echo "[$ok] $1: $ex arquivos_com_patch=$(estado) reinicios=${r:-0} temporarios=$tmp"; if [ $ok = FALHOU ]; then tail -5 $T/out.txt | sed "s/^/        /"; fi; }
mk_case orig;  run;                                   rep "1 container recriado (originais) -> restaura" 0 4 1
[ -s $T/fake/root/app/twin_silent_contacts.txt ] && echo "[OK] 1b lista devolvida" || echo "[FALHOU] 1b lista"
mk_case novo;  run;                                   rep "2 ja com os patches -> nada a fazer" 0 4 0
mk_case misto; run;                                   rep "3 estado misto -> aborta sem tocar" 1 1 0
mk_case outro; run;                                   rep "4 imagem diferente -> aborta sem tocar" 1 0 0
mk_case orig;  touch $T/fake/smoke_fail; run;         rep "5 verificacao falha -> volta aos originais" 1 0 2
mk_case orig;  touch $T/fake/unhealthy_after_restart; run; rep "6 nao fica healthy -> volta aos originais" 1 0 2
mk_case orig;  run CORRUPT_CP=1;                      rep "7 copia corrompida -> aborta sem tocar" 1 0 0
mk_case orig;  echo "x" > $T/bkp/handlers.py; run;    rep "8 copia de seguranca adulterada -> aborta sem tocar" 1 0 0
