#!/bin/bash
# Mudança 4: contatos silenciosos do Twin. Aplicação segura no container do backend. Uso:  bash aplicar_na_vps_m4.sh
# Pasta com: aplicar_m4.py, lista_silenciosos.txt e rollback_na_vps_m4.sh. O script copia o handlers.py do container (handlers.py.orig), gera o handlers.py.novo e confere os hashes.
# Nada é gravado no código em uso até o arquivo novo estar conferido DENTRO do container; qualquer falha reverte sozinha.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
H_ORIG=bf3ff6b771721ace8bde9cc3e525f80593f4511f2c88c47de4c92fdd438fc117   # handlers.py de produção depois da Mudança 2A
H_NEW=9eb1e67c626efd3fbcb204e91cb794649be32b7e2e31b0af50d7b0bca64e15b1
HP=/app/jobs/handlers.py
LP=/app/twin_silent_contacts.txt

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { for _ in $(seq 1 30); do sleep 5; [ "$(health)" = healthy ] && return 0; done; return 1; }
cleanup_tmp() { docker exec "$BK" rm -f "$HP.m4_new" "$LP.m4_new" >/dev/null 2>&1 || true; }
trap cleanup_tmp EXIT

back_out() {
  echo "PROBLEMA: $1. Revertendo para o original..."
  docker cp handlers.py.orig "$BK:$HP" || echo "ATENÇÃO: falha ao copiar o original; rode rollback_na_vps_m4.sh"
  docker restart "$BK" >/dev/null || true
  wait_healthy || echo "ATENÇÃO: o container não voltou healthy após a reversão"
  echo "hash handlers: $(sha_live $HP)"
  echo "REVERTIDO (esperado: $H_ORIG)"
  exit 1
}

echo "== 1. pré-condições (nada é alterado)"
[ "$(health)" = healthy ] || die "o container não está healthy"
for f in aplicar_m4.py lista_silenciosos.txt rollback_na_vps_m4.sh; do [ -s "$f" ] || die "falta o arquivo $f"; done
docker cp "$BK:$HP" handlers.py.orig
expect "handlers.py no container" "$(sha_live $HP)" "$H_ORIG"
expect "handlers.py.orig (cópia fiel)" "$(sha_file handlers.py.orig)" "$H_ORIG"
cp handlers.py.orig handlers.py.novo
python3 aplicar_m4.py || die "o aplicar_m4.py recusou (nada foi gravado no container)"
expect "handlers.py.novo" "$(sha_file handlers.py.novo)" "$H_NEW"
if docker exec "$BK" test -e "$LP"; then die "já existe $LP no container; confira antes de sobrescrever (nada foi alterado)"; fi
echo "OK"

echo "== 2. copia para nomes temporários e confere (o código em uso não muda)"
docker cp handlers.py.novo "$BK:$HP.m4_new"
docker cp lista_silenciosos.txt "$BK:$LP.m4_new"
expect "handlers temporário" "$(sha_live $HP.m4_new)" "$H_NEW"
expect "lista temporária" "$(sha_live $LP.m4_new)" "$(sha_file lista_silenciosos.txt)"
echo "OK"

echo "== 3. troca (cópia de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $HP $HP.m4_bak; mv $LP.m4_new $LP; mv $HP.m4_new $HP"; then
  docker cp handlers.py.orig "$BK:$HP" || true
  docker exec "$BK" rm -f "$LP" >/dev/null 2>&1 || true
  die "a troca falhou; original restaurado, sem reinício"
fi
if [ "$(sha_live $HP)" != "$H_NEW" ]; then
  docker cp handlers.py.orig "$BK:$HP" || true
  docker exec "$BK" rm -f "$LP" >/dev/null 2>&1 || true
  die "hash diverge depois da troca; original restaurado, sem reinício"
fi
echo "OK"

echo "== 4. reinicia e espera ficar healthy (máx. 150 s)"
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
docker restart "$BK" >/dev/null
wait_healthy || back_out "o container não ficou healthy"
echo "OK"

echo "== 5. verificação funcional dentro do container"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import os
import tempfile

import jobs.handlers as h

assert h._human_pause_minutes() >= 0  # a 2A continua presente
entradas = h._twin_silent_entries()
print("entradas na lista real:", len(entradas))
assert entradas, "a lista real está vazia"
assert all(h._twin_silent_contact(int(e), None) for e in entradas if e.isdigit() and len(e) <= 7)
with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
    f.write("# teste\n999991, +55 (11) 90000-1234\n")
os.environ["TWIN_SILENT_FILE"] = f.name
assert h._twin_silent_contact(999991, None) and h._twin_silent_contact(1, "5511900001234")
assert not h._twin_silent_contact(999992, "5511900001235")
os.unlink(f.name)
print("verificação funcional OK")
PY
echo "OK"

echo "== 6. hashes finais e logs desde o reinício"
expect "handlers.py final" "$(sha_live $HP)" "$H_NEW"
tracebacks=$(docker logs --since "$T0" "$BK" 2>&1 | grep -ciE 'traceback' || true)
[ "$tracebacks" = 0 ] || back_out "$tracebacks traceback(s) nos logs depois do reinício"
echo "SUCESSO: Mudança 4 aplicada. Lista em $LP (muda sem reiniciar). Para desfazer: bash rollback_na_vps_m4.sh"
