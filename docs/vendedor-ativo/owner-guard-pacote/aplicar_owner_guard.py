#!/usr/bin/env python3
"""Gera handlers.py.novo (do container): guarda de atividade do dono nos agentes da loja, B2B e Azusa + alerta ao dono por outra linha.
EDIÇÕES ANCORADAS no texto real da produção; cada âncora tem de aparecer EXATAMENTE 1 vez, senão aborta sem gravar nada.

Uso:  python3 aplicar_owner_guard.py PASTA   (PASTA tem handlers.py.lido; grava handlers.py.novo ao lado)
"""
import sys
from pathlib import Path

# (nome, âncora, substituição)
EDITS = [
    ("envio: roteia alerta ao dono + revalida o dono antes de transmitir",
     "    if not await _owner_audio_send_guard(db, payload, to, instance):\n        return\n    provider = get_whatsapp_provider()\n",
     "    if not await _owner_audio_send_guard(db, payload, to, instance):\n        return\n"
     "    from services import line_watch as _lw, owner_activity as _oa\n"
     "    instance = _lw.route_owner_alert(to, instance)      # alerta ao dono: outra linha no ar se a da loja caiu\n"
     "    if not await _oa.send_guard(db, payload, instance):  # o dono entrou durante a geração: não transmite\n"
     "        return\n"
     "    provider = get_whatsapp_provider()\n"),
    ("B2B/Azusa: confere o dono antes de gerar",
     '        if getattr(message.media_type, "value", message.media_type) != "text":\n            logger.info("Extra WhatsApp: somente texto nesta etapa")\n            return\n',
     '        if getattr(message.media_type, "value", message.media_type) != "text":\n            logger.info("Extra WhatsApp: somente texto nesta etapa")\n            return\n'
     "        from services import owner_activity as _oa\n"
     "        if not await _oa.pre_check(db, extra_agents[instance], contact_id, message_id, instance):\n"
     '            logger.info("Extra WhatsApp: dono ativo na conversa; agente não responde (instância %s)", instance)\n'
     "            return\n"),
    ("B2B/Azusa: marca o envio para revalidar",
     '                {"to": contact.phone, "content": result.reply, "instance": instance},\n',
     '                {"to": contact.phone, "content": result.reply, "instance": instance,\n'
     '                 **_oa.guard_payload(extra_agents[instance], contact_id, message_id)},\n'),
    ("loja: variável da marca de revalidação",
     "    reply_phone = contact.phone\n",
     "    reply_phone = contact.phone\n    _guard_extra: dict = {}\n"),
    ("loja: confere o dono antes de gerar (só no caminho do LLM; confirmação de pedido segue)",
     '        else:\n            result = await ai_orchestrator.run(\n                db=db,\n                user=owner,\n                message=message.content,\n                contact_id=contact_id,\n                agent_name="store",\n            )\n            reply = result.reply\n',
     '        else:\n            from services import owner_activity as _oa\n'
     '            if not await _oa.pre_check(db, "store", contact_id, message_id, instance):\n'
     '                logger.info("Loja: dono ativo na conversa; agente não responde (contato %s)", contact_id)\n'
     "                return\n"
     '            _guard_extra = _oa.guard_payload("store", contact_id, message_id)\n'
     '            result = await ai_orchestrator.run(\n                db=db,\n                user=owner,\n                message=message.content,\n                contact_id=contact_id,\n                agent_name="store",\n            )\n            reply = result.reply\n'),
    ("loja: marca o envio gerado pelo LLM",
     '            {"to": reply_phone, "content": reply, "instance": instance},\n        )\n',
     '            {"to": reply_phone, "content": reply, "instance": instance, **_guard_extra},\n        )\n'),
]


def build(text: str) -> str:
    if "owner_activity" in text:
        raise SystemExit("ABORTAR: parece que a guarda do dono já foi aplicada (não vou aplicar duas vezes)")
    for name, anchor, _ in EDITS:
        n = text.count(anchor)
        if n != 1:
            raise SystemExit(f"ABORTAR: '{name}': âncora encontrada {n} vez(es), esperado 1 (o handlers.py do container difere do esperado)")
    for _, anchor, new in EDITS:
        text = text.replace(anchor, new, 1)
    compile(text, "handlers.py", "exec")          # o resultado tem de ser Python válido
    return text


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    d = Path(sys.argv[1])
    (d / "handlers.py.novo").write_text(build((d / "handlers.py.lido").read_text(encoding="utf-8")), encoding="utf-8", newline="")
    print("gerado: handlers.py.novo")
