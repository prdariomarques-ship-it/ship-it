#!/bin/bash
# Recuperação: se o container do backend for RECRIADO a partir da imagem antiga, devolve os patches das Mudanças 2A, 3, 4 e 5 e a lista de contatos silenciosos.
# Uso:  bash recuperar_patches.sh /root/backup_twin_AAAAMMDD_HHMM      (a pasta criada pelo comando de cópia de segurança)
# Só age se os 4 arquivos do container forem EXATAMENTE os originais da imagem; confere o hash de cada cópia; reinicia o backend; reverte sozinho se falhar.
set -euo pipefail
BK=darioos-evolution-backend-1
SRC="${1:-}"
die() { echo "ABORTAR: $*"; exit 1; }
[ -n "$SRC" ] && [ -d "$SRC" ] || die "informe a pasta da cópia de segurança (ex.: bash recuperar_patches.sh /root/backup_twin_20261014_2122)"
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { for _ in $(seq 1 30); do sleep 5; [ "$(health)" = healthy ] && return 0; done; return 1; }

# caminho no container | nome na cópia | hash ORIGINAL da imagem | hash COM os patches
TABELA=(
"/app/jobs/handlers.py|handlers.py|f7b077199defc5c969aa7f142c9e64b73775bdb730d74b1c38333b1618eaf0a8|9eb1e67c626efd3fbcb204e91cb794649be32b7e2e31b0af50d7b0bca64e15b1"
"/app/services/messaging.py|messaging.py|5b72aae2fcf268a39ba8c013ae60eb4329713c6d8d752198625e97401a31f1a0|42397ce3f0bd22d0a87966fd6ac1bf7f85f15eeb33f42889d3ed8ec20d53f4ca"
"/app/agents/prompts/darius_twin.md|darius_twin.md|8639955aa1ae48c350ef2ae50715d61009ff4ec67062273eab36a3b1dee41e0b|2951896e864481da06615626bbd669015815228c8315171bcbfe2b38eae6c0ed"
"/app/agents/prompts/twin_conversation.md|twin_conversation.md|0ee24d0d8a72e6775cbbc189f74a6fa388fcc53d26edd487cd4a9d73ea607e19|ae8ea5208b22b4b062f90b90577c33a4ea7d7a7cb9389eb907168f98dfd7f6ed"
)
LISTA=/app/twin_silent_contacts.txt

echo "== 1. pré-condições (nada é alterado)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s "$SRC/twin_silent_contacts.txt" ] || die "falta twin_silent_contacts.txt na cópia"
JA=0; ORIG=0
for linha in "${TABELA[@]}"; do
  IFS='|' read -r CAM NOME HORIG HNOVO <<<"$linha"
  [ -s "$SRC/$NOME" ] || die "falta $NOME na cópia"
  [ "$(sha_file "$SRC/$NOME")" = "$HNOVO" ] || die "$NOME da cópia não é o esperado (hash diferente de $HNOVO)"
  VIVO=$(sha_live "$CAM")
  if [ "$VIVO" = "$HNOVO" ]; then JA=$((JA+1)); elif [ "$VIVO" = "$HORIG" ]; then ORIG=$((ORIG+1)); else die "$CAM no container tem hash $VIVO: nem o original nem o corrigido (a imagem mudou?); nada foi alterado"; fi
done
[ "$JA" = 4 ] && { echo "Os 4 arquivos já estão com os patches; nada a fazer."; exit 0; }
[ "$ORIG" = 4 ] || die "estado misto ($JA já com patch, $ORIG originais); confira à mão; nada foi alterado"
echo "OK: container com os 4 arquivos originais; cópia íntegra"

echo "== 2. copia para nomes temporários e confere (o código em uso não muda)"
for linha in "${TABELA[@]}"; do
  IFS='|' read -r CAM NOME HORIG HNOVO <<<"$linha"
  docker cp "$SRC/$NOME" "$BK:$CAM.rec_new"
  [ "$(sha_live "$CAM.rec_new")" = "$HNOVO" ] || { docker exec "$BK" sh -c "rm -f /app/jobs/handlers.py.rec_new /app/services/messaging.py.rec_new /app/agents/prompts/darius_twin.md.rec_new /app/agents/prompts/twin_conversation.md.rec_new"; die "cópia temporária de $NOME corrompida; nada foi alterado"; }
done
echo "OK"

echo "== 3. troca os 4 juntos (cópia .rec_bak de cada original dentro do container)"
CMD="set -e;"
for linha in "${TABELA[@]}"; do IFS='|' read -r CAM _ _ _ <<<"$linha"; CMD="$CMD cp -p $CAM $CAM.rec_bak;"; done
for linha in "${TABELA[@]}"; do IFS='|' read -r CAM _ _ _ <<<"$linha"; CMD="$CMD mv $CAM.rec_new $CAM;"; done
back_out() {
  echo "PROBLEMA: $1. Devolvendo os originais..."
  for linha in "${TABELA[@]}"; do IFS='|' read -r CAM _ _ _ <<<"$linha"; docker exec "$BK" sh -c "[ -f $CAM.rec_bak ] && cp -p $CAM.rec_bak $CAM" || true; done
  docker restart "$BK" >/dev/null || true; wait_healthy || echo "ATENÇÃO: o container não voltou healthy"
  echo "REVERTIDO"; exit 1
}
docker exec "$BK" sh -c "$CMD" || back_out "a troca falhou"
if ! docker exec "$BK" test -e "$LISTA"; then docker cp "$SRC/twin_silent_contacts.txt" "$BK:$LISTA"; fi
for linha in "${TABELA[@]}"; do
  IFS='|' read -r CAM NOME HORIG HNOVO <<<"$linha"
  [ "$(sha_live "$CAM")" = "$HNOVO" ] || back_out "hash de $CAM diverge depois da troca"
done
echo "OK"

echo "== 4. reinicia e espera ficar healthy (máx. 150 s)"
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
docker restart "$BK" >/dev/null
wait_healthy || back_out "o container não ficou healthy"
echo "OK"

echo "== 5. verificação funcional dentro do container"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import jobs.handlers as h
from agents.darius_twin import load_persona_prompt

t = load_persona_prompt()
assert "Aqui é o Twin, assistente do Dário" in t and "## Compromissos em nome do Dário" in t, "textos"
assert h._twin_silent_entries(), "lista vazia"
assert h._human_pause_minutes() >= 0
print("verificação funcional OK; entradas na lista:", len(h._twin_silent_entries()))
PY
tracebacks=$(docker logs --since "$T0" "$BK" 2>&1 | grep -ciE 'traceback' || true)
[ "$tracebacks" = 0 ] || back_out "$tracebacks traceback(s) nos logs depois do reinício"
echo "SUCESSO: patches das Mudanças 2A, 3, 4 e 5 devolvidos ao container."
