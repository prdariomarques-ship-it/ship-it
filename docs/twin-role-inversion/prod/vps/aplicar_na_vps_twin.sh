#!/bin/bash
# Gemeo: papeis + silencio + ato proibido (PRODUCAO). Uso:  bash aplicar_na_vps_twin.sh   (na pasta com os arquivos do pacote; ver LEIA-ME.md)
# REINICIA o backend (segundos). NAO envia mensagens e NAO escreve no banco. Edita agents/darius_twin.py e jobs/handlers.py (edicoes ancoradas) e cria
# agents/darius_twin_roles.py, agents/darius_twin_actions.py e orchestrator/twin_silence.py. Qualquer falha devolve tudo e reinicia de novo.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
TW=/app/agents/darius_twin.py; HND=/app/jobs/handlers.py; ROL=/app/agents/darius_twin_roles.py; ACT=/app/agents/darius_twin_actions.py; SIL=/app/orchestrator/twin_silence.py
ORIG_TW=c935113114ac5a7104ced158974e42f7d164c6b2619dce8b2cefc7eb459efb2c
ORIG_HND=ec6dd50c23ffae3dc28fc12d293acff85bc84dcca661ba43ab674519d4e4eb11
ESPERA_HEALTH=${ESPERA_HEALTH:-90}

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { local i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
trap 'docker exec "$BK" rm -f "$TW.tw_new" "$HND.tw_new" "$ROL.tw_new" "$ACT.tw_new" "$SIL.tw_new" >/dev/null 2>&1 || true' EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  docker cp darius_twin.py.orig "$BK:$TW" || echo "ATENCAO: falha ao copiar darius_twin.py"
  docker cp handlers.py.orig "$BK:$HND" || echo "ATENCAO: falha ao copiar handlers.py"
  docker exec "$BK" rm -f "$ROL" "$ACT" "$SIL" || true
  docker restart "$BK" >/dev/null || echo "ATENCAO: falha ao reiniciar"
  wait_healthy && echo "backend healthy de novo" || echo "ATENCAO: backend nao ficou healthy; rode rollback_twin.sh e olhe docker logs"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. confere os arquivos desta pasta e le os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container nao esta healthy"
for f in aplicar_twin_roles.py darius_twin_roles.py darius_twin_actions.py twin_silence.py SHA256SUMS; do [ -s "$f" ] || die "falta $f nesta pasta"; done
sha256sum -c SHA256SUMS >/dev/null 2>&1 || die "SHA256SUMS nao confere: algum arquivo desta pasta foi alterado ou corrompido"
for p in $ROL $ACT $SIL; do docker exec "$BK" test ! -e "$p" || die "$p ja existe no container (patch ja aplicado?)"; done
for f in darius_twin.py:$TW handlers.py:$HND; do
  n=${f%%:*}; p=${f#*:}
  docker cp "$BK:$p" "$n.lido"; [ -s "$n.lido" ] || die "nao consegui ler $p"
  expect "$n (copia fiel)" "$(sha_live $p)" "$(sha_file $n.lido)"
done
expect "darius_twin.py do container e o original conhecido" "$(sha_file darius_twin.py.lido)" "$ORIG_TW"
mkdir -p lido && cp darius_twin.py.lido lido/darius_twin.py && cp handlers.py.lido lido/handlers.py
FLAG=""
if [ "$(sha_file handlers.py.lido)" != "$ORIG_HND" ]; then
  grep -q '_oa.send_guard' handlers.py.lido || die "handlers.py do container nao e o original conhecido nem o original + owner-guard (hash $(sha_file handlers.py.lido)); nada foi alterado"
  echo "aviso: handlers.py ja tem o owner-guard; aplicando so por ancoras"; FLAG="--sem-hash-handlers"
fi
rm -rf novo; python3 aplicar_twin_roles.py --origem lido --saida novo $FLAG || die "o aplicar_twin_roles.py recusou (nada foi gravado no container)"
for n in darius_twin.py handlers.py; do mv "$n.lido" "$n.orig"; printf '%s  %s\n' "$(sha_file $n.orig)" "$n" >> hashes_antes_twin.tmp; done
mv hashes_antes_twin.tmp hashes_antes_twin.txt
echo "OK (originais guardados como *.orig)"

echo "== 2. copia para nomes temporarios e confere (o codigo em uso nao muda)"
docker cp novo/darius_twin.py "$BK:$TW.tw_new"; docker cp novo/handlers.py "$BK:$HND.tw_new"
docker cp darius_twin_roles.py "$BK:$ROL.tw_new"; docker cp darius_twin_actions.py "$BK:$ACT.tw_new"; docker cp twin_silence.py "$BK:$SIL.tw_new"
expect "darius_twin temporario" "$(sha_live $TW.tw_new)" "$(sha_file novo/darius_twin.py)"
expect "handlers temporario" "$(sha_live $HND.tw_new)" "$(sha_file novo/handlers.py)"
expect "roles temporario" "$(sha_live $ROL.tw_new)" "$(sha_file darius_twin_roles.py)"
expect "actions temporario" "$(sha_live $ACT.tw_new)" "$(sha_file darius_twin_actions.py)"
expect "silence temporario" "$(sha_live $SIL.tw_new)" "$(sha_file twin_silence.py)"
echo "OK"

echo "== 3. troca (copias de seguranca dentro do container; nunca sobrescreve uma copia existente)"
docker exec "$BK" test ! -e "$TW.tw_bak" || die "$TW.tw_bak ja existe (aplicacao anterior?)"
if ! docker exec "$BK" sh -c "set -e; cp -p $TW $TW.tw_bak; cp -p $HND $HND.tw_bak; mv $ROL.tw_new $ROL; mv $ACT.tw_new $ACT; mv $SIL.tw_new $SIL; mv $TW.tw_new $TW; mv $HND.tw_new $HND"; then back_out "a troca falhou"; fi
expect "darius_twin final" "$(sha_live $TW)" "$(sha_file novo/darius_twin.py)"
expect "handlers final" "$(sha_live $HND)" "$(sha_file novo/handlers.py)"
echo "OK"

echo "== 4. reinicia o backend e espera ficar healthy"
docker restart "$BK" >/dev/null || back_out "o restart falhou"
wait_healthy || back_out "o backend nao ficou healthy em ${ESPERA_HEALTH}s"
echo "OK"

echo "== 5. verificacao funcional (so LE; nao envia mensagem, nao escreve no banco)"
docker exec -i "$BK" python - <<'PY' || back_out "a verificacao funcional falhou"
import inspect
import jobs.handlers as h
import agents.darius_twin as t
from agents import darius_twin_actions as a, darius_twin_roles as r
from orchestrator import twin_silence as s

src = inspect.getsource(h.twin_autopilot_check)
assert "twin_silence" in src and "build_twin_history" in src and "blocked_action" in src, "handler sem as edicoes"
assert r.ROLE_RULES in t.ROLE_RULES
assert r.guard_role_inversion("Ainda não, tô na mesma.\n\nVc tá melhorando aí?", "Como vc está?", [], contact_name="X") == "Ainda não, tô na mesma."
assert r.guard_role_inversion("Entendi, Adriane. Ok.", "Oi, pastor Adriane, tudo bem", [], contact_name="Y") == "Entendi. Ok."
assert r.guard_role_inversion("Oi, Maria! Tudo bem?", "Oi Maria", [], contact_name="Maria Silva") == "Oi, Maria! Tudo bem?"
assert a.blocked_action("Pode emitir").category == "autorizacao" and a.blocked_action("Vou ver isso e te falo.") is None
assert s.silence_reason("👋", has_prior_outbound=True) and s.silence_reason("Bom dia, tudo bem?", has_prior_outbound=True) is None
print("papeis, silencio e ato proibido carregados")
PY
echo "OK"
echo "SUCESSO: o Gemeo agora (1) rotula quem escreveu cada fala, (2) nao usa o apelido do dono para chamar o contato nem devolve pergunta de saude, (3) cala diante de robo/despedida/alerta do sistema, (4) segura autorizar/pedir CPF-conta/cobrar/prazo. Para desfazer: bash rollback_twin.sh"
