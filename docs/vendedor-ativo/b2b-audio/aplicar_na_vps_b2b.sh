#!/bin/bash
# Libera o áudio da instância b2b-sales (o agente B2B passa a entender e responder áudios como responde texto).
# Uso:  bash aplicar_na_vps_b2b.sh   (na pasta com aplicar_b2b.py). Muda config.py e provider.py do container e REINICIA o backend (segundos).
# Nada é gravado no container até os arquivos novos estarem conferidos DENTRO dele; qualquer falha devolve tudo e reinicia de novo.
set -euo pipefail
BK=darioos-evolution-backend-1
cd "$(dirname "$0")"
CFG=/app/utils/config.py; PRV=/app/providers/whatsapp/evolution/provider.py
ESPERA_HEALTH=${ESPERA_HEALTH:-90}

die() { echo "ABORTAR: $*"; exit 1; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
sha_live() { docker exec "$BK" sha256sum "$1" | awk '{print $1}'; }
expect() { [ -n "$2" ] && [ "$2" = "$3" ] || die "$1: obtido '${2:-vazio}', esperado '$3'"; }
health() { docker inspect -f '{{.State.Health.Status}}' "$BK" 2>/dev/null || echo desconhecido; }
wait_healthy() { local i=0; while [ "$i" -lt "$ESPERA_HEALTH" ]; do [ "$(health)" = healthy ] && return 0; sleep 1; i=$((i+1)); done; return 1; }
trap 'docker exec "$BK" rm -f "$CFG.b2b_new" "$PRV.b2b_new" >/dev/null 2>&1 || true' EXIT
back_out() {
  echo "PROBLEMA: $1. Devolvendo o original..."
  docker cp config.py.orig "$BK:$CFG" || echo "ATENÇÃO: falha ao copiar config.py"
  docker cp provider.py.orig "$BK:$PRV" || echo "ATENÇÃO: falha ao copiar provider.py"
  docker restart "$BK" >/dev/null || echo "ATENÇÃO: falha ao reiniciar"
  wait_healthy && echo "backend healthy de novo" || echo "ATENÇÃO: backend não ficou healthy; rode rollback_b2b.sh e olhe docker logs"
  echo "REVERTIDO"
  exit 1
}

echo "== 1. lê os originais do container (somente leitura)"
[ "$(health)" = healthy ] || die "o container não está healthy"
[ -s aplicar_b2b.py ] || die "falta o aplicar_b2b.py nesta pasta"
for f in config.py:$CFG provider.py:$PRV; do
  n=${f%%:*}; p=${f#*:}
  docker cp "$BK:$p" "$n.lido"
  [ -s "$n.lido" ] || die "não consegui ler $p"
  expect "$n (cópia fiel)" "$(sha_live $p)" "$(sha_file $n.lido)"
done
python3 aplicar_b2b.py . || die "o aplicar_b2b.py recusou (nada foi gravado no container)"
for n in config.py provider.py; do mv "$n.lido" "$n.orig"; printf '%s  %s\n' "$(sha_file $n.orig)" "$n" >> hashes_antes_b2b.tmp; done
mv hashes_antes_b2b.tmp hashes_antes_b2b.txt
echo "OK (originais guardados como *.orig)"

echo "== 2. copia para nomes temporários e confere (o código em uso não muda)"
docker cp config.py.novo "$BK:$CFG.b2b_new"; docker cp provider.py.novo "$BK:$PRV.b2b_new"
expect "config temporário" "$(sha_live $CFG.b2b_new)" "$(sha_file config.py.novo)"
expect "provider temporário" "$(sha_live $PRV.b2b_new)" "$(sha_file provider.py.novo)"
echo "OK"

echo "== 3. troca (cópias de segurança dentro do container)"
if ! docker exec "$BK" sh -c "set -e; cp -p $CFG $CFG.b2b_bak; cp -p $PRV $PRV.b2b_bak; mv $CFG.b2b_new $CFG; mv $PRV.b2b_new $PRV"; then back_out "a troca falhou"; fi
expect "config final" "$(sha_live $CFG)" "$(sha_file config.py.novo)"
expect "provider final" "$(sha_live $PRV)" "$(sha_file provider.py.novo)"
echo "OK"

echo "== 4. reinicia o backend e espera ficar healthy"
docker restart "$BK" >/dev/null || back_out "o restart falhou"
wait_healthy || back_out "o backend não ficou healthy em ${ESPERA_HEALTH}s"
echo "OK"

echo "== 5. verificação funcional dentro do container (sem rede: o envio ao Evolution é substituído)"
docker exec -i "$BK" python - <<'PY' || back_out "a verificação funcional falhou"
import asyncio, base64
from providers.whatsapp.evolution.provider import EvolutionProvider
from utils.config import get_settings

s = get_settings()
assert s.evolution_media_extra_instances == "b2b-sales", s.evolution_media_extra_instances
p = EvolutionProvider()
calls = []
async def fake_post(path, body, instance=None):
    calls.append(instance)
    return {"base64": base64.b64encode(b"audio").decode(), "mimetype": "audio/ogg"}
p._post = fake_post
async def run():
    ok = await p.download_media({"id": "x"}, instance="b2b-sales")
    assert ok == (b"audio", "audio/ogg"), ok
    assert await p.download_media({"id": "x"}, instance="azusa-church") is None
    assert await p.download_media({"id": "x"}, instance=s.evolution_instance) is not None
asyncio.run(run())
print("b2b-sales liberada; azusa-church continua bloqueada; instância da loja continua valendo; chamadas:", calls)
PY
echo "OK"
echo "SUCESSO: o agente B2B agora entende áudios da instância b2b-sales. Para desfazer: bash rollback_b2b.sh"
