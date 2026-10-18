#!/usr/bin/env python3
"""Gera config.py.novo e main.py.novo (do container) para o vigia de linhas, com EDIÇÕES ANCORADAS e padrões de produção.

Uso:  LW_INSTANCES="a,b" LW_PHONE="5511..." python3 aplicar_linewatch.py PASTA   (PASTA tem config.py.lido e main.py.lido)
Aborta sem gravar NADA se uma âncora não aparecer exatamente 1 vez ou se já estiver aplicado.
Em produção o vigia nasce LIGADO (line_watch_enabled=True) com as instâncias e o telefone informados; no repositório o padrão é desligado.
Só o import do job entra no main.py (registra o handler); a primeira rodada é semeada pelo script de aplicação.
"""
import os
import sys
from pathlib import Path

CONFIG_ANCHOR = "    stt_background_enabled: bool = False\n"
CONFIG_ADD = '''    # Vigia das linhas do WhatsApp (services/line_watch.py): consulta o estado de cada instancia no Evolution a cada rodada e avisa o
    # dono quando uma cair (estado diferente de "open"), por OUTRA linha que esteja no ar. Desligado por padrao.
    line_watch_enabled: bool = {enabled}
    # Instancias vigiadas, separadas por virgula. Vazio = a da loja e a pessoal configuradas.
    line_watch_instances: str = {instances}
    line_watch_interval_seconds: int = 120
    line_watch_confirm_checks: int = 2          # rodadas seguidas fora do ar antes de avisar (evita alarme falso)
    line_watch_repeat_minutes: int = 60         # lembrete enquanto a linha continuar fora
    # Telefone (com DDI) que recebe o alerta; vazio = usa whatsapp_owner_alert_phone.
    line_watch_alert_phone: str = {phone}
'''
MAIN_ANCHOR = "import observation.scheduler  # noqa: F401 - register the observation.tick job handler\n"
MAIN_ADD = "import jobs.line_watch_job  # noqa: F401 - register the lines.watch job handler\n"


def once(text: str, anchor: str, what: str) -> None:
    n = text.count(anchor)
    if n != 1:
        raise SystemExit(f"ABORTAR: {what}: âncora encontrada {n} vez(es), esperado 1 (o arquivo do container difere do esperado)")


def build(config: str, main: str, *, enabled=False, instances="", phone="") -> tuple[str, str]:
    if "line_watch" in config or "line_watch" in main:
        raise SystemExit("ABORTAR: parece que o vigia já foi aplicado (não vou aplicar duas vezes)")
    once(config, CONFIG_ANCHOR, "config.py")
    once(main, MAIN_ANCHOR, "main.py")
    add = CONFIG_ADD.replace("{enabled}", repr(bool(enabled))).replace("{instances}", '"' + instances + '"').replace("{phone}", '"' + phone + '"')
    return config.replace(CONFIG_ANCHOR, CONFIG_ANCHOR + add, 1), main.replace(MAIN_ANCHOR, MAIN_ANCHOR + MAIN_ADD, 1)


def main_cli(folder: str) -> None:
    d = Path(folder)
    read = lambda name: (d / f"{name}.lido").read_text(encoding="utf-8")
    instances, phone = os.environ.get("LW_INSTANCES", ""), os.environ.get("LW_PHONE", "")
    if not phone.isdigit() or not 10 <= len(phone) <= 15:
        raise SystemExit("ABORTAR: LW_PHONE deve ter só dígitos (10 a 15, com DDI)")
    if not instances.strip():
        raise SystemExit("ABORTAR: LW_INSTANCES vazio")
    config, main = build(read("config.py"), read("main.py"), enabled=True, instances=instances, phone=phone)
    (d / "config.py.novo").write_text(config, encoding="utf-8", newline="")
    (d / "main.py.novo").write_text(main, encoding="utf-8", newline="")
    print("gerados: config.py.novo main.py.novo")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main_cli(sys.argv[1])
