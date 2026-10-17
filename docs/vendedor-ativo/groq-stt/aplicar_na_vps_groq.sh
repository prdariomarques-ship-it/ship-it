#!/bin/bash
# Groq STT: aplicação segura no container do backend. Uso:  bash aplicar_na_vps_groq.sh   (na pasta com aplicar_groq.py e groq.py)
# Muda 3 arquivos (edições ancoradas), cria 1 (groq.py) e acrescenta 3 linhas ao /app/.env. EXIGE reiniciar o backend (alguns segundos).
# A chave é pedida com digitação OCULTA e só trafega por stdin: não vai para histórico, arquivo da VPS fora do /app/.env, nem tela.
# Nada é gravado no container até os arquivos novos estarem conferidos DENTRO dele; qualquer falha devolve tudo e reinicia de novo.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
CFG=/app/utils/config.py; FAC=/app/providers/stt/factory.py; RTR=/app/webhooks/router.py; GRQ=/app/providers/stt/groq.py; ENVF=/app/.env
GROQ_SHA_ESPERADO=10dd87cfc6bf7659fc887c35668c0d0c41662df508bde0dffe2a2f23afc29249   # groq.py do repositório (commit 1762b73)
INSTANCIAS="${STT_INSTANCES_ALVO:-MARQUESCOLOR,b2b-sales}"
ESPERA_HEALTH=${ESPERA_HEALTH:-90}

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { local i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
cleanup_tmp() { docker exec "$BK" rm -f "$CFG.groq_new" "$FAC.groq_new" "$RTR.groq_new" "$GRQ.groq_new" >/dev/null 2>&1 || true; }
trap cleanup_tmp EXIT
restore_all() {
  docker cp config.py.orig "$BK:$CFG" || echo "ATENÇÃO: falha ao copiar config.py"
  docker cp factory.py.orig "$BK:$FAC" || echo "ATENÇÃO: falha ao copiar factory.py"
  docker cp router.py.orig "$BK:$RTR" || echo "ATENÇÃO: falha ao copiar router.py"
  docker exec "$BK" rm -f "$GRQ" || true
  if [ "${ENV_CRIADO:-0}" = 1 ]; then docker exec "$BK" rm -f "$ENVF" || true
  elif [ "${ENV_SALVO:-0}" = 1 ]; then docker exec "$BK" sh -c "cp -p $ENVF.groq_bak $ENVF" || echo "ATENÇÃO: falha ao restaurar o .env"; fi
}
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  restore_all
  docker restart "$BK" >/dev/null || echo "ATENÇÃO: falha ao reiniciar"
  wait_healthy && echo "backend healthy de novo" || echo "ATENÇÃO: backend não ficou healthy; rode rollback_groq.sh e olhe docker logs"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. lê os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_groq.py ] && [ -s groq.py ] || die "faltam aplicar_groq.py e/ou groq.py nesta pasta"
expect "groq.py desta pasta" "$(sha_file groq.py)" "$GROQ_SHA_ESPERADO"
docker exec "$BK" test ! -e "$GRQ" || die "$GRQ já existe no container (Groq já aplicado?)"
for f in config.py:$CFG factory.py:$FAC router.py:$RTR; do
  n=${f%%:*}; p=${f#*:}
  docker cp "$BK:$p" "$n.lido"
  [ -s "$n.lido" ] || die "não consegui ler $p"
  expect "$n (cópia fiel)" "$(sha_live $p)" "$(sha_file $n.lido)"
done
python3 aplicar_groq.py . || die "o aplicar_groq.py recusou (nada foi gravado no container)"
for n in config.py factory.py router.py; do mv "$n.lido" "$n.orig"; printf '%s  %s\n' "$(sha_file $n.orig)" "$n" >> hashes_antes_groq.tmp; done
mv hashes_antes_groq.tmp hashes_antes_groq.txt
echo "OK (originais guardados como *.orig)"

echo "== 2. chave (digitação oculta) e conferência do .env"
if [ -z "${GROQ_API_KEY:-}" ]; then read -rsp "Cole a chave NOVA da Groq (não aparece na tela) e tecle Enter: " GROQ_API_KEY; echo; fi
case "$GROQ_API_KEY" in gsk_*) ;; *) die "a chave deve começar com gsk_";; esac
[ "${#GROQ_API_KEY}" -ge 30 ] || die "a chave parece curta demais"
ENV_CRIADO=0; ENV_SALVO=0
if docker exec "$BK" test -f "$ENVF"; then
  [ "$(docker exec "$BK" grep -c -E '^(STT_PROVIDER|GROQ_API_KEY|STT_INSTANCES)=' "$ENVF" || true)" = 0 ] || die "o $ENVF já define STT_PROVIDER/GROQ_API_KEY/STT_INSTANCES; ajuste à mão"
  docker exec "$BK" sh -c "cp -p $ENVF $ENVF.groq_bak"; ENV_SALVO=1
else
  ENV_CRIADO=1; echo criado > env_criado_groq.txt
fi
echo "OK"

echo "== 3. copia para nomes temporários e confere (o código em uso não muda)"
docker cp config.py.novo "$BK:$CFG.groq_new"; docker cp factory.py.novo "$BK:$FAC.groq_new"; docker cp router.py.novo "$BK:$RTR.groq_new"; docker cp groq.py "$BK:$GRQ.groq_new"
expect "config temporário" "$(sha_live $CFG.groq_new)" "$(sha_file config.py.novo)"
expect "factory temporário" "$(sha_live $FAC.groq_new)" "$(sha_file factory.py.novo)"
expect "router temporário" "$(sha_live $RTR.groq_new)" "$(sha_file router.py.novo)"
expect "groq temporário" "$(sha_live $GRQ.groq_new)" "$GROQ_SHA_ESPERADO"
echo "OK"

echo "== 4. troca (cópias de segurança dentro do container) e grava as 3 linhas no .env"
if ! docker exec "$BK" sh -c "set -e; cp -p $CFG $CFG.groq_bak; cp -p $FAC $FAC.groq_bak; cp -p $RTR $RTR.groq_bak; mv $CFG.groq_new $CFG; mv $FAC.groq_new $FAC; mv $RTR.groq_new $RTR; mv $GRQ.groq_new $GRQ"; then
  back_out "a troca falhou"
fi
if ! printf '\nSTT_PROVIDER=groq\nSTT_INSTANCES=%s\nGROQ_API_KEY=%s\n' "$INSTANCIAS" "$GROQ_API_KEY" | docker exec -i "$BK" sh -c "cat >> $ENVF && chmod 600 $ENVF"; then
  back_out "não consegui gravar o .env"
fi
expect "config final" "$(sha_live $CFG)" "$(sha_file config.py.novo)"
expect "factory final" "$(sha_live $FAC)" "$(sha_file factory.py.novo)" 
expect "router final" "$(sha_live $RTR)" "$(sha_file router.py.novo)"
echo "OK"

echo "== 5. reinicia o backend e espera ficar healthy"
docker restart "$BK" >/dev/null || back_out "o restart falhou"
wait_healthy || back_out "o backend não ficou healthy em ${ESPERA_HEALTH}s"
echo "OK"

echo "== 6. verificação funcional dentro do container (inclui 1 chamada real à Groq com 1 s de silêncio)"
docker exec -i -e ALVO_INSTANCIAS="$INSTANCIAS" "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import asyncio, io, os, wave
from providers.stt.base import STTProviderError
from providers.stt.factory import get_stt_provider
from utils.config import get_settings
import webhooks.router  # noqa: F401  (importa sem erro)

s = get_settings(); p = get_stt_provider()
assert s.stt_provider == "groq", s.stt_provider
assert s.stt_instances == os.environ["ALVO_INSTANCIAS"], s.stt_instances
assert p is not None and p.name == "groq" and p.enabled, "provedor groq não está habilitado (chave não chegou?)"
buf = io.BytesIO()
with wave.open(buf, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 16000)
try:
    print("resposta da Groq:", repr(asyncio.run(p.transcribe(buf.getvalue(), "audio/wav"))))
except STTProviderError as exc:
    msg = str(exc)
    # silêncio => "transcricao vazia"/"alucinacao" significa que a chamada CHEGOU e a chave foi aceita
    assert "vazia" in msg or "alucina" in msg, msg
    print("a Groq respondeu (silêncio sem texto, como esperado):", msg)
print("provedor groq habilitado; instâncias:", s.stt_instances)
PY
echo "OK"

echo "SUCESSO: transcrição Groq ligada para: $INSTANCIAS. Para desfazer: bash rollback_groq.sh"
