#!/bin/bash
# Testa a LÓGICA dos scripts do Groq com um "docker" de mentira (fakedocker.sh), usando os arquivos REAIS do repositório no estado anterior
# (git show 6977f14). Uso (de dentro do repositório):  bash docs/vendedor-ativo/groq-stt/harness_groq.sh
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../.." && pwd)"; cd "$HERE"
KEY="gsk_$(printf 'a%.0s' $(seq 1 40))"
new_case() {
  T=$(mktemp -d); mkdir -p $T/bin $T/dir $T/fake/root/app/utils $T/fake/root/app/providers/stt $T/fake/root/app/webhooks
  cp fakedocker.sh $T/bin/docker; chmod +x $T/bin/docker
  ( cd $ROOT; git show 6977f14:backend/utils/config.py > $T/fake/root/app/utils/config.py; git show 6977f14:backend/providers/stt/factory.py > $T/fake/root/app/providers/stt/factory.py; git show 6977f14:backend/webhooks/router.py > $T/fake/root/app/webhooks/router.py )
  cp aplicar_groq.py aplicar_na_vps_groq.sh rollback_groq.sh $T/dir/; cp $ROOT/backend/providers/stt/groq.py $T/dir/groq.py
}
state() { cat $T/fake/root/app/utils/config.py $T/fake/root/app/providers/stt/factory.py $T/fake/root/app/webhooks/router.py | sha256sum | cut -c1-12; }
runapply() { ( export FAKE=$T/fake PATH=$T/bin:$PATH GROQ_API_KEY="$KEY" ESPERA_HEALTH=2 "$@"; cd $T/dir; bash aplicar_na_vps_groq.sh > $T/out.txt 2>&1; echo "exit=$?" >> $T/out.txt ); }
runrb() { ( export FAKE=$T/fake PATH=$T/bin:$PATH ESPERA_HEALTH=2; cd $T/dir; bash rollback_groq.sh > $T/out2.txt 2>&1; echo "exit=$?" >> $T/out2.txt ); }
report() {  # nome ; exit esperado ; antes|mudou ; reinícios esperados
  ex=$(grep -o 'exit=[0-9]*' $T/out.txt | tail -1); now=$(state); tmp=$(find $T/fake/root/app -name '*.groq_new' | wc -l); rs=$(grep -c restarted $T/fake/events 2>/dev/null || true); rs=${rs:-0}
  ok=OK; [ "$ex" = "exit=$2" ] || ok=FALHOU
  if [ "$3" = antes ]; then [ "$now" = "$ORIG" ] || ok=FALHOU; else [ "$now" != "$ORIG" ] || ok=FALHOU; fi
  [ "$tmp" = 0 ] && [ "$rs" = "$4" ] || ok=FALHOU
  grep -q "$KEY" $T/out.txt && ok=FALHOU && echo "        !!! a chave apareceu na saída"
  echo "[$ok] $1: $ex arquivos=$3 temporarios=$tmp reinicios=$rs"; [ "$ok" = FALHOU ] && tail -6 $T/out.txt | sed 's/^/        /'
}
new_case; ORIG=$(state); runapply;                                        report "1 sucesso (env criado)" 0 mudou 1
grep -q 'groq' $T/fake/root/app/providers/stt/factory.py && [ -f $T/fake/root/app/providers/stt/groq.py ] && grep -q '^GROQ_API_KEY=' $T/fake/root/app/.env && [ "$(stat -c %a $T/fake/root/app/.env)" = 600 ] && echo "[OK] 1b groq.py presente, .env com a chave e permissão 600" || echo "[FALHOU] 1b"
new_case; printf 'OPENAI_API_KEY=x\nOUTRA=1' > $T/fake/root/app/.env; ORIG=$(state); runapply; report "2 sucesso (env existente sem quebra de linha final)" 0 mudou 1
grep -q '^OPENAI_API_KEY=x$' $T/fake/root/app/.env && grep -q '^STT_PROVIDER=groq$' $T/fake/root/app/.env && grep -q '^OUTRA=1$' $T/fake/root/app/.env && echo "[OK] 2b linhas antigas preservadas e novas separadas" || { echo "[FALHOU] 2b"; cat $T/fake/root/app/.env; }
new_case; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "3 verificação funcional falha -> restaura e reinicia" 1 antes 2
[ ! -f $T/fake/root/app/providers/stt/groq.py ] && [ ! -f $T/fake/root/app/.env ] && echo "[OK] 3b groq.py e .env criado removidos" || echo "[FALHOU] 3b"
new_case; printf 'A=1\n' > $T/fake/root/app/.env; ORIG=$(state); touch $T/fake/smoke_fail $T/fake/healthy_again_after_second_restart; runapply; report "4 falha funcional com .env existente -> .env volta" 1 antes 2
[ "$(cat $T/fake/root/app/.env)" = "A=1" ] && echo "[OK] 4b .env restaurado igual" || { echo "[FALHOU] 4b"; cat $T/fake/root/app/.env; }
new_case; sed -i 's/if stt is None or not stt.enabled or inbound.media_key is None:/if stt is None:/' $T/fake/root/app/webhooks/router.py; ORIG=$(state); runapply; report "5 router divergente (âncora some) -> aborta sem tocar" 1 antes 0
new_case; sed -i 's/^_PROVIDERS: dict\[str, type\[STTProvider\]\] = {}/_PROVIDERS: dict[str, type[STTProvider]] = {"outro": object}/' $T/fake/root/app/providers/stt/factory.py; ORIG=$(state); runapply; report "6 factory com outro backend -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply CORRUPT_CP=1;                            report "7 cópia temporária corrompida -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply FAIL_SWAP=1; sleep 0; report "8 troca falha -> restaura e reinicia" 1 antes 1
new_case; ORIG=$(state); touch $T/fake/unhealthy; runapply;               report "9 container sem health -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply GROQ_API_KEY="chave_errada";             report "10 chave com formato errado -> aborta sem tocar" 1 antes 0
new_case; printf 'STT_PROVIDER=outro\n' > $T/fake/root/app/.env; ORIG=$(state); runapply; report "11 .env já define STT_PROVIDER -> aborta sem tocar" 1 antes 0
new_case; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && grep -q 'exit=0' $T/out2.txt && [ ! -f $T/fake/root/app/providers/stt/groq.py ] && [ ! -f $T/fake/root/app/.env ] && echo "[OK] 12 rollback depois do sucesso: arquivos, groq.py e .env criado desfeitos" || { echo "[FALHOU] 12 rollback"; tail -4 $T/out2.txt; }
new_case; printf 'A=1\n' > $T/fake/root/app/.env; ORIG=$(state); runapply; runrb
[ "$(state)" = "$ORIG" ] && [ "$(cat $T/fake/root/app/.env)" = "A=1" ] && echo "[OK] 13 rollback com .env existente: .env volta igual" || { echo "[FALHOU] 13"; cat $T/fake/root/app/.env; tail -3 $T/out2.txt; }
new_case; ORIG=$(state); runapply; O1=$(sha256sum $T/dir/factory.py.orig | cut -c1-12); runapply; O2=$(sha256sum $T/dir/factory.py.orig | cut -c1-12)
[ "$O1" = "$O2" ] && grep -q 'exit=1' $T/out.txt && echo "[OK] 14 repetir o apply: aborta e o .orig guardado não é sobrescrito" || echo "[FALHOU] 14"
runrb; [ "$(state)" = "$ORIG" ] && echo "[OK] 14b rollback ainda funciona depois da repetição" || echo "[FALHOU] 14b"
