#!/usr/bin/env python3
"""Gera as versões novas de config.py, factory.py e router.py (do container) com EDIÇÕES ANCORADAS: só insere o necessário para o Groq.

Uso:  python3 aplicar_groq.py PASTA      (PASTA tem config.py.lido, factory.py.lido, router.py.lido; grava *.novo ao lado)
Aborta sem gravar NADA se qualquer âncora não aparecer exatamente 1 vez, se já estiver aplicado, ou se o router não importar get_settings.
"""
import sys
from pathlib import Path

CONFIG_ANCHOR = "    stt_background_enabled: bool = False\n"
CONFIG_ADD = '''    # Instancias WhatsApp cujo audio PODE ser enviado ao servico de transcricao (nomes separados por virgula, ex.:
    # "MARQUESCOLOR,b2b-sales"). Vazio = todas (comportamento anterior). O audio sai do servidor, entao a lista existe para manter de
    # fora conversas pessoais (familia, igreja) sem depender de cada fluxo lembrar disso.
    stt_instances: str = ""

    # Groq (Whisper hospedado). Usado quando stt_provider="groq". A chave vem SO de variavel de ambiente (GROQ_API_KEY);
    # sem chave o provedor fica desabilitado (enabled=False) e o webhook segue como se nao houvesse STT.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_stt_model: str = "whisper-large-v3-turbo"
    groq_stt_language: str = "pt"
    groq_stt_timeout_seconds: float = 20.0
'''
FACTORY_IMPORT_ANCHOR = "from providers.stt.base import STTProvider\n"
FACTORY_IMPORT_NEW = FACTORY_IMPORT_ANCHOR + "from providers.stt.groq import GroqSTTProvider\n"
FACTORY_DICT_ANCHOR = "_PROVIDERS: dict[str, type[STTProvider]] = {}\n"
FACTORY_DICT_NEW = '_PROVIDERS: dict[str, type[STTProvider]] = {"groq": GroqSTTProvider}\n'
ROUTER_ANCHOR = '    if stt is None or not stt.enabled or inbound.media_key is None:\n        return ""\n'
ROUTER_ADD = '''    allowed = {name.strip() for name in get_settings().stt_instances.split(",") if name.strip()}
    if allowed and (inbound.instance or "") not in allowed:
        return ""  # instancia fora da lista: o audio NAO sai do servidor
'''


def once(text: str, anchor: str, what: str) -> None:
    n = text.count(anchor)
    if n != 1:
        raise SystemExit(f"ABORTAR: {what}: âncora encontrada {n} vez(es), esperado 1 (o arquivo do container difere do esperado)")


def build(config: str, factory: str, router: str) -> tuple[str, str, str]:
    if "groq" in factory.lower() or "stt_instances" in config or "stt_instances" in router:
        raise SystemExit("ABORTAR: parece que o Groq já foi aplicado (não vou aplicar duas vezes)")
    if "from utils.config import get_settings" not in router:
        raise SystemExit("ABORTAR: router.py não importa get_settings")
    once(config, CONFIG_ANCHOR, "config.py")
    once(factory, FACTORY_IMPORT_ANCHOR, "factory.py (import)")
    once(factory, FACTORY_DICT_ANCHOR, "factory.py (_PROVIDERS)")
    once(router, ROUTER_ANCHOR, "router.py")
    config = config.replace(CONFIG_ANCHOR, CONFIG_ANCHOR + CONFIG_ADD, 1)
    factory = factory.replace(FACTORY_IMPORT_ANCHOR, FACTORY_IMPORT_NEW, 1).replace(FACTORY_DICT_ANCHOR, FACTORY_DICT_NEW, 1)
    router = router.replace(ROUTER_ANCHOR, ROUTER_ANCHOR + ROUTER_ADD, 1)
    return config, factory, router


def main(folder: str) -> None:
    d = Path(folder)
    read = lambda name: (d / f"{name}.lido").read_text(encoding="utf-8")
    new = build(read("config.py"), read("factory.py"), read("router.py"))
    for name, text in zip(("config.py", "factory.py", "router.py"), new):
        (d / f"{name}.novo").write_text(text, encoding="utf-8", newline="")
    print("gerados: config.py.novo factory.py.novo router.py.novo")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
