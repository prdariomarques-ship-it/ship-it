#!/bin/bash
# Mudança 5 (texto do Twin): aplicação segura no container do backend. Uso:  bash aplicar_na_vps_m5.sh   (na pasta que tem o aplicar_m5.py)
# Só o twin_conversation.md muda. O Twin lê o texto a cada resposta: NÃO reinicia nada. Nada é gravado no container até o arquivo novo estar conferido
# DENTRO dele; qualquer falha devolve o original sozinha.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
PB=/app/agents/prompts/twin_conversation.md
B_ORIG_ESPERADO=ce47ba7e8b8fc5d54d05b1549b4a8a5d3715b4e2b138e901c87b5228e0fffc0d   # twin_conversation.md depois da Mudança 3

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
cleanup_tmp() { docker exec "$BK" rm -f "$PB.m5_new" >/dev/null 2>&1 || true; }
trap cleanup_tmp EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  docker cp twin_conversation.md.orig "$BK:$PB" || echo "ATENÇÃO: falha ao copiar o original; rode rollback_m5.sh"
  echo "hash twin_conversation.md: $(sha_live $PB)  (original $B_ORIG_ESPERADO)"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. lê o original do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_m5.py ] || die "falta o aplicar_m5.py nesta pasta"
docker cp "$BK:$PB" twin_conversation.md.lido
[ -s twin_conversation.md.lido ] || die "não consegui ler o texto do container"
B_ORIG=$(sha_file twin_conversation.md.lido)
expect "twin_conversation.md (cópia fiel)" "$(sha_live $PB)" "$B_ORIG"
expect "twin_conversation.md é o da Mudança 3 (se a Mudança 5 já foi aplicada, o .orig guardado NÃO é sobrescrito)" "$B_ORIG" "$B_ORIG_ESPERADO"
mv twin_conversation.md.lido twin_conversation.md.orig
printf '%s  twin_conversation.md\n' "$B_ORIG" > hashes_antes_m5.txt
echo "hash original: $B_ORIG"

echo "== 2. gera o arquivo novo (aborta se o bloco já existe ou o da Mudança 3 não bate)"
cp twin_conversation.md.orig twin_conversation.md.novo
python3 aplicar_m5.py || die "o aplicar_m5.py recusou (nada foi gravado no container)"
B_NEW=$(sha_file twin_conversation.md.novo)

echo "== 3. copia para nome temporário e confere (o texto em uso não muda)"
docker cp twin_conversation.md.novo "$BK:$PB.m5_new"
expect "twin_conversation temporário" "$(sha_live $PB.m5_new)" "$B_NEW"
echo "OK"

echo "== 4. troca (cópia de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $PB $PB.m5_bak; mv $PB.m5_new $PB"; then
  back_out "a troca falhou"
fi
if [ "$(sha_live $PB)" != "$B_NEW" ]; then back_out "hash diverge depois da troca"; fi
echo "OK"

echo "== 5. verificação dentro do container (sem reiniciar)"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
from agents.darius_twin import load_persona_prompt

t = load_persona_prompt()
checks = {
    "bloco da Mudança 5 presente": "## Compromissos em nome do Dário" in t,
    "regra: não prometer": 'Não escreva "vou fazer"' in t,
    "Mudança 3 continua presente": "Aqui é o Twin, assistente do Dário" in t and "## Fatos autorizados sobre o Dário" in t,
    "e-mail do dono presente": "dariomneto@hotmail.com" in t,
}
for nome, ok in checks.items():
    print("OK " if ok else "FALHOU", nome)
assert all(checks.values()), [n for n, ok in checks.items() if not ok]
print("tamanho do prompt (caracteres):", len(t))
PY
echo "OK"

echo "== 6. hash final"
expect "twin_conversation.md final" "$(sha_live $PB)" "$B_NEW"
echo "SUCESSO: regra de compromissos aplicada (vale a partir da próxima resposta). Para desfazer: bash rollback_m5.sh"
