#!/bin/bash
# Reproduz os testes da Mudança 4 sobre os arquivos REAIS de producao: aplica a 2A e depois a 4 sobre o handlers.py de producao (bases em ../mudanca2a/bases-producao/,
# conferidas por SHA-256) e roda test_m4_producao.py (que reaproveita os fixtures de test_m2a_producao.py). Uso (na raiz do repositorio, com as dependencias instaladas):
#    bash docs/vendedor-ativo/mudanca4/rodar_testes_m4.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
M2A="$HERE/../mudanca2a"
ROOT="$(cd "$HERE/../../.." && pwd)"
BASES="$M2A/bases-producao"
(cd "$BASES" && sha256sum -c SHA256SUMS)
TMP="$(mktemp -d)"
(cd "$ROOT/backend" && tar --exclude='__pycache__' --exclude='.pytest_cache' -cf - .) | (cd "$TMP" && tar -xf -)
WORK="$(mktemp -d)"
cp "$BASES/handlers.py" "$WORK/handlers.py.novo"; cp "$BASES/messaging.py" "$WORK/messaging.py.novo"
(cd "$WORK" && python3 "$M2A/aplicar_m2a.py" >/dev/null && python3 "$HERE/aplicar_m4.py")
cp "$WORK/handlers.py.novo" "$TMP/jobs/handlers.py"
cp "$WORK/messaging.py.novo" "$TMP/services/messaging.py"
cp "$BASES/router.py" "$TMP/webhooks/router.py"; cp "$BASES/provider.py" "$TMP/providers/whatsapp/evolution/provider.py"
cp "$BASES/base.py" "$TMP/agents/base.py"; cp "$BASES/service.py" "$TMP/orchestrator/service.py"
cp "$BASES/models_message.py" "$TMP/models/message.py"; cp "$BASES/repositories_message.py" "$TMP/repositories/message.py"
cat > "$TMP/jobs/owner_audio_dependencies.py" <<'PY'
"""STUB: o modulo real existe so na producao."""


class JobDependencyPending(Exception):
    def __init__(self, message: str, retry_after: float = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after
PY
cp "$M2A/test_m2a_producao.py" "$TMP/tests/test_m2a_producao.py"; cp "$HERE/test_m4_producao.py" "$TMP/tests/test_m4_producao.py"
cd "$TMP"
python -m pytest -q -p no:cacheprovider tests/test_m4_producao.py tests/test_m2a_producao.py
