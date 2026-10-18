#!/usr/bin/env python3
"""Gera handlers.py.novo (do container) com UMA edição ancorada: alerta ao dono sai por outra linha no ar quando a padrão (loja) está fora.

Uso:  python3 aplicar_roteamento.py PASTA   (PASTA tem handlers.py.lido; grava handlers.py.novo ao lado)
Aborta sem gravar NADA se a âncora não aparecer exatamente 1 vez ou se já estiver aplicado.
"""
import sys
from pathlib import Path

ANCHOR = "    alert_dedup_key = payload.get('_twin_alert_dedup_key')\n"
ADD = '''    if instance is None and alert_dedup_key:
        # Alerta ao proprietario sem linha explicita: sai pela padrao (loja). Se o vigia viu a padrao fora do ar, sai por outra no ar
        # (so o transporte muda; o escopo da reserva continua em _twin_alert_instance). Sem leitura recente do vigia: comportamento de sempre.
        from services import line_watch
        from utils.config import get_settings as _get_settings

        instance = line_watch.alert_instance(_get_settings()) or None
'''


def build(text: str) -> str:
    if "line_watch.alert_instance" in text:
        raise SystemExit("ABORTAR: parece que o roteamento já foi aplicado (não vou aplicar duas vezes)")
    n = text.count(ANCHOR)
    if n != 1:
        raise SystemExit(f"ABORTAR: handlers.py: âncora encontrada {n} vez(es), esperado 1 (o arquivo do container difere do esperado)")
    return text.replace(ANCHOR, ANCHOR + ADD, 1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    d = Path(sys.argv[1])
    (d / "handlers.py.novo").write_text(build((d / "handlers.py.lido").read_text(encoding="utf-8")), encoding="utf-8", newline="")
    print("gerado: handlers.py.novo")
