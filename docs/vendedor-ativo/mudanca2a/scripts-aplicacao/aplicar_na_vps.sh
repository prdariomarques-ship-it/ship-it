#!/bin/bash
# Mudança 2A: aplicação segura no container do backend. Uso:  bash aplicar_na_vps.sh   (na pasta que tem os .orig, os .novo e este arquivo)
# Nada é gravado no código em uso até que os arquivos novos estejam conferidos DENTRO do container; qualquer falha reverte sozinha.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
H_ORIG=f7b077199defc5c969aa7f142c9e64b73775bdb730d74b1c38333b1618eaf0a8
M_ORIG=5b72aae2fcf268a39ba8c013ae60eb4329713c6d8d752198625e97401a31f1a0
H_NEW=bf3ff6b771721ace8bde9cc3e525f80593f4511f2c88c47de4c92fdd438fc117
M_NEW=42397ce3f0bd22d0a87966fd6ac1bf7f85f15eeb33f42889d3ed8ec20d53f4ca
HP=/app/jobs/handlers.py
MP=/app/services/messaging.py

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { for _ in $(seq 1 30); do sleep 5; [ "$(health)" = healthy ] && return 0; done; return 1; }
cleanup_tmp() { docker exec "$BK" rm -f "$HP.m2a_new" "$MP.m2a_new" >/dev/null 2>&1 || true; }
trap cleanup_tmp EXIT

back_out() {
  echo "PROBLEMA: $1. Revertendo para os originais..."
  docker cp handlers.py.orig "$BK:$HP" && docker cp messaging.py.orig "$BK:$MP" || echo "ATENÇÃO: falha ao copiar os originais; rode rollback_na_vps.sh"
  docker restart "$BK" >/dev/null || true
  wait_healthy || echo "ATENÇÃO: o container não voltou healthy após a reversão"
  echo "hash handlers: $(sha_live $HP)"; echo "hash messaging: $(sha_live $MP)"
  echo "REVERTIDO (esperado: $H_ORIG e $M_ORIG)"
  exit 1
}

echo "== 1. pré-condições (nada é alterado)"
[ "$(health)" = healthy ] || die "o container não está healthy"
for f in handlers.py.orig handlers.py.novo messaging.py.orig messaging.py.novo rollback_na_vps.sh; do [ -s "$f" ] || die "falta o arquivo $f"; done
expect "handlers.py.orig" "$(sha_file handlers.py.orig)" "$H_ORIG"
expect "messaging.py.orig" "$(sha_file messaging.py.orig)" "$M_ORIG"
expect "handlers.py.novo" "$(sha_file handlers.py.novo)" "$H_NEW"
expect "messaging.py.novo" "$(sha_file messaging.py.novo)" "$M_NEW"
expect "handlers.py no container" "$(sha_live $HP)" "$H_ORIG"
expect "messaging.py no container" "$(sha_live $MP)" "$M_ORIG"
echo "OK"

echo "== 2. copia para nomes temporários e confere (o código em uso não muda)"
docker cp handlers.py.novo "$BK:$HP.m2a_new"
docker cp messaging.py.novo "$BK:$MP.m2a_new"
expect "handlers temporário" "$(sha_live $HP.m2a_new)" "$H_NEW"
expect "messaging temporário" "$(sha_live $MP.m2a_new)" "$M_NEW"
echo "OK"

echo "== 3. troca os dois arquivos juntos (com cópia de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $HP $HP.m2a_bak; cp -p $MP $MP.m2a_bak; mv $HP.m2a_new $HP; mv $MP.m2a_new $MP"; then
  docker cp handlers.py.orig "$BK:$HP" && docker cp messaging.py.orig "$BK:$MP" || true
  die "a troca falhou; originais restaurados, sem reinício"
fi
if [ "$(sha_live $HP)" != "$H_NEW" ] || [ "$(sha_live $MP)" != "$M_NEW" ]; then
  docker cp handlers.py.orig "$BK:$HP" && docker cp messaging.py.orig "$BK:$MP" || true
  die "hash diverge depois da troca; originais restaurados, sem reinício"
fi
echo "OK"

echo "== 4. reinicia e espera ficar healthy (máx. 150 s)"
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
docker restart "$BK" >/dev/null
wait_healthy || back_out "o container não ficou healthy"
echo "OK"

echo "== 5. verificação funcional dentro do container"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import asyncio
import inspect
from datetime import datetime, timezone

import jobs.handlers as h
import services.messaging as m

assert "external_id" in inspect.signature(m.persist_outbound_message).parameters, "assinatura do envio"
assert h._unverified_contact_data("Meu e-mail é mneto@hotmail.com", []) == "email"
assert h._unverified_contact_data("Meu e-mail é dariomneto@hotmail.com", []) is None
assert h._audio_transcript_unreliable("Devemos outro bem.", min_words=5)
assert h._is_bot_self_intro("Oi! Aqui é o assistente automático do Dário")
assert h._sent_message_id({"key": {"id": "X"}}) == "X"
print("pausa configurada (min):", h._human_pause_minutes())

from database.session import async_session_factory


async def main():
    async with async_session_factory() as db:
        a = await h._human_active_recently(db, 1, "MARQUESCOLOR")
        b = await h._human_outbound_after(db, 1, "MARQUESCOLOR", datetime.now(timezone.utc))
        print("consultas ao banco ok:", a, b)

asyncio.run(main())
print("verificação funcional OK")
PY
echo "OK"

echo "== 6. hashes finais e logs desde o reinício"
expect "handlers.py final" "$(sha_live $HP)" "$H_NEW"
expect "messaging.py final" "$(sha_live $MP)" "$M_NEW"
tracebacks=$(docker logs --since "$T0" "$BK" 2>&1 | grep -ciE 'traceback' || true)
[ "$tracebacks" = 0 ] || back_out "$tracebacks traceback(s) nos logs depois do reinício"
echo "SUCESSO: Mudança 2A aplicada. Para desligar a pausa na hora:  docker exec $BK sh -c \"echo 0 > /app/human_pause_minutes.txt\"   (religar: echo 30 > o mesmo arquivo)"
