#!/bin/bash
# Mudança 3 (texto do Twin): aplicação segura no container do backend. Uso:  bash aplicar_na_vps_m3a.sh   (na pasta que tem o aplicar_m3a.py)
# Os textos são lidos a cada resposta: NÃO reinicia nada. Nada é gravado no container até os arquivos novos estarem conferidos DENTRO dele;
# qualquer falha devolve os originais sozinha.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
PA=/app/agents/prompts/darius_twin.md
PB=/app/agents/prompts/twin_conversation.md

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
cleanup_tmp() { docker exec "$BK" rm -f "$PA.m3a_new" "$PB.m3a_new" >/dev/null 2>&1 || true; }
trap cleanup_tmp EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo os originais..."
  docker cp darius_twin.md.orig "$BK:$PA" && docker cp twin_conversation.md.orig "$BK:$PB" || echo "ATENÇÃO: falha ao copiar os originais; rode rollback_m3a.sh"
  echo "hash darius_twin.md:       $(sha_live $PA)  (original $A_ORIG)"
  echo "hash twin_conversation.md: $(sha_live $PB)  (original $B_ORIG)"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. lê os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_m3a.py ] || die "falta o aplicar_m3a.py nesta pasta"
docker cp "$BK:$PB" twin_conversation.md.lido
if grep -q "FICHA-M3A:INICIO" twin_conversation.md.lido; then rm -f twin_conversation.md.lido; die "o bloco da Mudança 3 já está no container; os .orig guardados NÃO foram sobrescritos"; fi
docker cp "$BK:$PA" darius_twin.md.orig
mv twin_conversation.md.lido twin_conversation.md.orig
[ -s darius_twin.md.orig ] && [ -s twin_conversation.md.orig ] || die "não consegui ler os textos do container"
A_ORIG=$(sha_file darius_twin.md.orig); B_ORIG=$(sha_file twin_conversation.md.orig)
expect "darius_twin.md (cópia fiel)" "$(sha_live $PA)" "$A_ORIG"
expect "twin_conversation.md (cópia fiel)" "$(sha_live $PB)" "$B_ORIG"
printf '%s  darius_twin.md\n%s  twin_conversation.md\n' "$A_ORIG" "$B_ORIG" > hashes_antes.txt
echo "hash original darius_twin.md:       $A_ORIG"
echo "hash original twin_conversation.md: $B_ORIG"
echo "linhas: $(wc -l < darius_twin.md.orig) / $(wc -l < twin_conversation.md.orig)  (visto antes: 1857 / 66)"

echo "== 2. gera os arquivos novos (aborta se algum trecho do manual não bater)"
cp darius_twin.md.orig darius_twin.md.novo; cp twin_conversation.md.orig twin_conversation.md.novo
python3 aplicar_m3a.py || die "o aplicar_m3a.py recusou (nada foi gravado no container)"
A_NEW=$(sha_file darius_twin.md.novo); B_NEW=$(sha_file twin_conversation.md.novo)

echo "== 3. copia para nomes temporários e confere (o texto em uso não muda)"
docker cp darius_twin.md.novo "$BK:$PA.m3a_new"
docker cp twin_conversation.md.novo "$BK:$PB.m3a_new"
expect "darius_twin temporário" "$(sha_live $PA.m3a_new)" "$A_NEW"
expect "twin_conversation temporário" "$(sha_live $PB.m3a_new)" "$B_NEW"
echo "OK"

echo "== 4. troca os dois juntos (cópia de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $PA $PA.m3a_bak; cp -p $PB $PB.m3a_bak; mv $PA.m3a_new $PA; mv $PB.m3a_new $PB"; then
  back_out "a troca falhou"
fi
if [ "$(sha_live $PA)" != "$A_NEW" ] || [ "$(sha_live $PB)" != "$B_NEW" ]; then back_out "hash diverge depois da troca"; fi
echo "OK"

echo "== 5. verificação dentro do container (o Twin lê os textos a cada resposta; não precisa reiniciar)"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
from agents.darius_twin import load_persona_prompt

t = load_persona_prompt()
checks = {
    "bloco novo presente": "## Fatos autorizados sobre o Dário" in t and "## Presença do Dário" in t,
    "identidade: Twin": "Aqui é o Twin, assistente do Dário" in t,
    "frase antiga 1 removida": "Responder em primeira pessoa como se fosse eu mesmo" not in t,
    "frase antiga 2 removida": 'Nunca dizer espontaneamente "sou um assistente"' not in t,
    "frase antiga 3 removida": "Sou o Dário, seguindo com vc aqui" not in t,
    "e-mail do dono presente": "dariomneto@hotmail.com" in t,
}
for nome, ok in checks.items():
    print("OK " if ok else "FALHOU", nome)
assert all(checks.values()), [n for n, ok in checks.items() if not ok]
print("tamanho do prompt (caracteres):", len(t))
PY
echo "OK"

echo "== 6. hashes finais"
expect "darius_twin.md final" "$(sha_live $PA)" "$A_NEW"
expect "twin_conversation.md final" "$(sha_live $PB)" "$B_NEW"
echo "SUCESSO: textos do Twin atualizados (valem a partir da próxima resposta). Para desfazer: bash rollback_m3a.sh"
