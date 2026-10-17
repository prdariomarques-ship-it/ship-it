#!/usr/bin/env python3
"""Libera o download de áudio da instância b2b-sales (EDIÇÕES ANCORADAS em config.py e provider.py do container).

Uso:  python3 aplicar_b2b.py PASTA   (PASTA tem config.py.lido e provider.py.lido; grava *.novo ao lado)
Aborta sem gravar NADA se uma âncora não aparecer exatamente 1 vez, se já estiver aplicado, ou se o provider não importar get_settings.
No container, o padrão da nova configuração é "b2b-sales" (sem precisar de .env); a variável EVOLUTION_MEDIA_EXTRA_INSTANCES continua mandando.
"""
import sys
from pathlib import Path

CONFIG_ANCHOR = "    stt_background_enabled: bool = False\n"
CONFIG_ADD = '''    # Instancias ALEM da loja e da pessoal cujo audio recebido o backend pode baixar para transcrever (nomes separados por virgula,
    # ex.: "b2b-sales"). Vazio = so as duas instancias configuradas (comportamento anterior). Liberar uma instancia aqui faz o agente
    # dela passar a entender e responder audios como responde texto.
    evolution_media_extra_instances: str = "{default}"
'''
PROVIDER_ANCHOR = "        if instance and instance not in {self._instance, self._personal_instance}:\n            return None\n"
PROVIDER_NEW = '''        extra = {name.strip() for name in get_settings().evolution_media_extra_instances.split(",") if name.strip()}
        if instance and instance not in {self._instance, self._personal_instance} | extra:
            return None
'''


def once(text: str, anchor: str, what: str) -> None:
    n = text.count(anchor)
    if n != 1:
        raise SystemExit(f"ABORTAR: {what}: âncora encontrada {n} vez(es), esperado 1 (o arquivo do container difere do esperado)")


def build(config: str, provider: str, default: str = "") -> tuple[str, str]:
    if "evolution_media_extra_instances" in config or "evolution_media_extra_instances" in provider:
        raise SystemExit("ABORTAR: parece que a liberação já foi aplicada (não vou aplicar duas vezes)")
    if "get_settings" not in provider:
        raise SystemExit("ABORTAR: provider.py não importa get_settings")
    once(config, CONFIG_ANCHOR, "config.py")
    once(provider, PROVIDER_ANCHOR, "provider.py")
    config = config.replace(CONFIG_ANCHOR, CONFIG_ANCHOR + CONFIG_ADD.replace("{default}", default), 1)
    provider = provider.replace(PROVIDER_ANCHOR, PROVIDER_NEW, 1)
    return config, provider


def main(folder: str) -> None:
    d = Path(folder)
    read = lambda name: (d / f"{name}.lido").read_text(encoding="utf-8")
    config, provider = build(read("config.py"), read("provider.py"), default="b2b-sales")
    (d / "config.py.novo").write_text(config, encoding="utf-8", newline="")
    (d / "provider.py.novo").write_text(provider, encoding="utf-8", newline="")
    print("gerados: config.py.novo provider.py.novo")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
