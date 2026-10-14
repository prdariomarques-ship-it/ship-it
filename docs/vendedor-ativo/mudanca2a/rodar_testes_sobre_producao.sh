#!/bin/bash
# Reproduz os testes da Mudança 2A sobre os arquivos REAIS de produção (bases em bases-producao/, conferidas por SHA-256):
# 1) aplica aplicar_m2a.py sobre as bases de handlers.py e messaging.py (que confere o hash do resultado);
# 2) monta uma cópia do backend da candidata com esses dois arquivos e as demais bases de produção por cima;
# 3) roda test_m2a_producao.py nessa cópia. Uso (na raiz do repositório, com as dependências do backend instaladas):
#    bash docs/vendedor-ativo/mudanca2a/rodar_testes_sobre_producao.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
BASES="$HERE/bases-producao"
(cd "$BASES" && sha256sum -c SHA256SUMS)
TMP="$(mktemp -d)"
(cd "$ROOT/backend" && tar --exclude='__pycache__' --exclude='.pytest_cache' -cf - .) | (cd "$TMP" && tar -xf -)
WORK="$(mktemp -d)"
cp "$BASES/handlers.py" "$WORK/handlers.py.novo"
cp "$BASES/messaging.py" "$WORK/messaging.py.novo"
(cd "$WORK" && python3 "$HERE/aplicar_m2a.py")
cp "$WORK/handlers.py.novo" "$TMP/jobs/handlers.py"
cp "$WORK/messaging.py.novo" "$TMP/services/messaging.py"
cp "$BASES/router.py" "$TMP/webhooks/router.py"
cp "$BASES/provider.py" "$TMP/providers/whatsapp/evolution/provider.py"
cp "$BASES/base.py" "$TMP/agents/base.py"
cp "$BASES/service.py" "$TMP/orchestrator/service.py"
cp "$BASES/models_message.py" "$TMP/models/message.py"
cp "$BASES/repositories_message.py" "$TMP/repositories/message.py"
# O modulo real existe so na producao; sem ele o handler do Twin nao importa na copia de teste.
cat > "$TMP/jobs/owner_audio_dependencies.py" <<'PY'
"""STUB: o modulo real existe so na producao."""


class JobDependencyPending(Exception):
    def __init__(self, message: str, retry_after: float = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after
PY
cp "$HERE/test_m2a_producao.py" "$TMP/tests/test_m2a_producao.py"
cd "$TMP"
python -m pytest -q -p no:cacheprovider tests/test_m2a_producao.py
