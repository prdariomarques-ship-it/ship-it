#!/usr/bin/env python3
"""Gera as versoes corrigidas de darius_twin.py e handlers.py DE PRODUCAO (somente leitura dos originais; escreve em --saida).

Edicoes ancoradas: cada ancora tem de aparecer EXATAMENTE uma vez, senao aborta sem escrever nada. O hash dos originais e conferido.
Parte aditiva: rotulos de autoria no historico ([Dario]/[Gemeo]), regra de papeis no prompt, remocao do apelido do dono usado como vocativo e da pergunta
de saude devolvida; e, DEPOIS dos guardas que a producao ja tem (twin_autoreply_gate, twin_finance_guard, twin_commitment_guard), dois blocos novos:
silencio (robo/menu/alerta do proprio sistema/despedida pura) e ato proibido (autorizar, pedir CPF/conta, cobrar, confirmar deposito, prazo, acao inventada).
Os 223 envios reais de 16-23/10 passam por TODOS os guardas de producao atuais (financeiro 0, compromisso 0, contraparte automatica 2).

Uso: python3 aplicar_twin_roles.py --origem DIR_COM_ORIGINAIS --saida DIR_DE_SAIDA
"""
import argparse
import hashlib
import sys
from pathlib import Path

SHA = {"darius_twin.py": "c935113114ac5a7104ced158", "handlers.py": "ec6dd50c23ffae3dc28fc12d"}   # prefixos do sha256 dos originais

TWIN_EDITS = [
    ("import",
     "from providers.llm.factory import chat_with_fallback\n",
     "from providers.llm.factory import chat_with_fallback\nfrom agents.darius_twin_roles import CONTACT_NOT_OWNER, ROLE_RULES, guard_role_inversion, role_guard_enabled\n"),
    ("persona",
     '    return _HTML_COMMENT.sub("", text).strip() + "\\n\\n" + conversation.strip()\n',
     '    return _HTML_COMMENT.sub("", text).strip() + "\\n\\n" + conversation.strip() + "\\n\\n" + ROLE_RULES\n'),
    ("linha_do_contato",
     '                content=f"Você está respondendo, pelo WhatsApp, para: {contact_name}.",\n',
     '                content=f"Você está respondendo, pelo WhatsApp, para: {contact_name}." + CONTACT_NOT_OWNER,\n'),
    ("resposta_final",
     '        raise TwinReplyUnavailable("LLM returned no usable reply")\n    return reply\n',
     '        raise TwinReplyUnavailable("LLM returned no usable reply")\n'
     '    # Papeis (agents/darius_twin_roles.py): tira o apelido do dono usado como vocativo e a pergunta de saude devolvida a quem nao disse estar doente.\n'
     '    guarded = guard_role_inversion(\n'
     '        reply, message, [m.content for m in history if m.role == "user"],\n'
     '        drop_health_question=role_guard_enabled(), contact_name=contact_name,\n'
     '    )\n'
     '    if guarded != reply:\n'
     '        logger.warning("Twin reply adjusted by the role-inversion guard")\n'
     '    if not guarded:\n'
     '        raise TwinReplyUnavailable("reply was only a health question returned to the contact")\n'
     '    return guarded\n'),
]
HANDLERS_EDITS = [
    ("import",
     "    from agents.darius_twin import TwinReplyUnavailable, generate_darius_reply\n",
     "    from agents.darius_twin import TwinReplyUnavailable, generate_darius_reply\n    from agents.darius_twin_roles import build_twin_history\n"),
    ("silencio",
     "    is_risky, reason = is_high_risk_for_impersonation(message.content, risk_history_texts(history, message_id))\n",
     "    from orchestrator import twin_silence\n"
     "    _quiet = twin_silence.silence_reason(\n"
     "        message.content or '', has_prior_outbound=any(m.direction == MessageDirection.OUTBOUND for m in history if m.id != message_id)\n"
     "    ) if twin_silence.silence_enabled() else None\n"
     "    if _quiet:\n"
     "        # robo/menu/fila, alerta do proprio sistema ou despedida pura: sem resposta, sem retencao e sem alerta (orchestrator/twin_silence.py)\n"
     "        await _owner_audio_clear_pending(db, contact, _twin_pending_snapshot, instance)\n"
     "        await db.commit()\n"
     "        await record_log(db, source='twin_autopilot', level='info',\n"
     "                         message=f'Sem resposta automática — {_quiet}', payload={'contact_id': contact_id, 'instance': instance})\n"
     "        return\n"
     "    is_risky, reason = is_high_risk_for_impersonation(message.content, risk_history_texts(history, message_id))\n"),
    ("ato_proibido",
     "        from orchestrator.twin_commitment_guard import reply_makes_commitment\n"
     "        _commit = None if is_risky else reply_makes_commitment(reply)\n"
     "        if _commit:\n"
     "            _blocked_draft = reply\n"
     "            is_risky, reason = (True, f'compromisso: {_commit}')\n"
     "            reply = ''\n",
     "        from orchestrator.twin_commitment_guard import reply_makes_commitment\n"
     "        _commit = None if is_risky else reply_makes_commitment(reply)\n"
     "        if _commit:\n"
     "            _blocked_draft = reply\n"
     "            is_risky, reason = (True, f'compromisso: {_commit}')\n"
     "            reply = ''\n"
     "        from agents.darius_twin_actions import action_guard_enabled, blocked_action\n"
     "        _act = blocked_action(reply) if (not is_risky and action_guard_enabled()) else None\n"
     "        if _act:\n"
     "            # autorizar/emitir, pedir agencia-conta-CPF, cobrar, confirmar deposito, prazo, 'ja segui': ato que o Gemeo nunca pratica\n"
     "            _blocked_draft = reply\n"
     "            is_risky, reason = (True, f'ato proibido ao Gêmeo: {_act.category}')\n"
     "            reply = ''\n"),
    ("historico_com_autoria",
     "        chat_history = [ChatMessage(role='user' if m.direction == MessageDirection.INBOUND else 'assistant', content=twin_history_content(m, _owner_audio_history_content(m))) for m in history if twin_history_content(m, _owner_audio_history_content(m)) and m.id != message_id]\n",
     "        chat_history = build_twin_history(history, content_of=lambda m: twin_history_content(m, _owner_audio_history_content(m)), exclude_id=message_id)\n"),
]


def apply(name: str, text: str, edits) -> str:
    for label, old, new in edits:
        if text.count(old) != 1:
            sys.exit(f"ABORTADO: ancora '{label}' de {name} aparece {text.count(old)} vez(es) (esperado 1). Nada foi escrito.")
        text = text.replace(old, new)
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", required=True, type=Path)
    ap.add_argument("--saida", required=True, type=Path)
    ap.add_argument("--sem-hash-handlers", action="store_true",
                    help="nao exige o sha256 do handlers.py original (use se outro patch, ex. owner-guard, ja o alterou); as ancoras continuam obrigatorias")
    args = ap.parse_args()
    out = {}
    for name, edits in (("darius_twin.py", TWIN_EDITS), ("handlers.py", HANDLERS_EDITS)):
        raw = (args.origem / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if not digest.startswith(SHA[name]) and not (name == "handlers.py" and args.sem_hash_handlers):
            sys.exit(f"ABORTADO: {name} nao e o original esperado (sha256 {digest[:24]}, esperado {SHA[name]}...). Nada foi escrito.")
        out[name] = apply(name, raw.decode("utf-8"), edits)
    args.saida.mkdir(parents=True, exist_ok=True)
    for name, text in out.items():
        compile(text, name, "exec")                    # sintaxe valida antes de gravar
        (args.saida / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"ok {name}: sha256 {hashlib.sha256(text.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
