"""Inversão de papéis do Gêmeo (caso "Gerente LIBINA", msg 15424).

O contato perguntou ao dono se ele tinha melhorado. O Gêmeo respondeu pelo dono e depois devolveu "Vc tá melhorando aí?" como se o contato
estivesse doente. Aqui: (1) a autoria entra no contexto; (2) o prompt e os exemplos dizem quem é o sujeito; (3) a rede de segurança tira a
pergunta de saúde devolvida a quem não disse estar doente; (4) fatos do PRÓPRIO dono, vindos de outras conversas, continuam sendo usados.

`chat_with_fallback` só existe na fábrica de LLM de PRODUÇÃO; o símbolo é injetado antes de importar `agents.darius_twin` (como em
test_style_distill.py). Nenhum LLM real, nenhum envio, nenhum dado de produção.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import providers.llm.factory as llm_factory
from agents import darius_twin_roles as roles
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from models.user import User, UserRole
from providers.llm.base import ChatMessage
from services import style_context
from utils.config import get_settings

BUGGY_REPLY = "Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também. Vc tá melhorando aí?"
OWNER_FACT = "Febre não baixou ontem à noite, tá ruim de engolir também."
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def twin(monkeypatch):
    """`agents.darius_twin` importável + um LLM falso que registra o que recebeu e devolve `llm.reply`."""
    llm = SimpleNamespace(reply=BUGGY_REPLY, calls=[])

    async def fake_chat(messages, tools=None):
        llm.calls.append(messages)
        return SimpleNamespace(content=llm.reply)

    monkeypatch.setattr(llm_factory, "chat_with_fallback", fake_chat, raising=False)
    import agents.darius_twin as darius_twin

    monkeypatch.setattr(darius_twin, "chat_with_fallback", fake_chat)
    monkeypatch.setattr(darius_twin, "load_persona_prompt", lambda: "PERSONA")
    llm.module = darius_twin
    return llm


def _row(direction, content="x", *, human=False, auto=False, id=1):
    return SimpleNamespace(id=id, direction=direction, content=content, sent_by_human=human, is_autopilot_reply=auto)


# ----------------------------------------------------------------------------------------------------------- autoria no histórico

def test_history_labels_owner_and_twin_and_leaves_unknown_and_inbound_untouched():
    rows = [
        _row(MessageDirection.INBOUND, "oi", id=1),
        _row(MessageDirection.OUTBOUND, "digitado pelo dono", human=True, id=2),
        _row(MessageDirection.OUTBOUND, "resposta do gêmeo", auto=True, id=3),
        _row(MessageDirection.OUTBOUND, "sem origem registrada", id=4),
        _row(MessageDirection.INBOUND, "pendente", id=5),
    ]
    history = roles.build_twin_history(rows, content_of=lambda r: r.content, exclude_id=5)
    assert [(m.role, m.content) for m in history] == [
        ("user", "oi"),
        ("assistant", "[Dário] digitado pelo dono"),
        ("assistant", "[Gêmeo] resposta do gêmeo"),
        ("assistant", "sem origem registrada"),          # nunca se adivinha a autoria
    ]


def test_autopilot_wins_over_human_flag_like_the_handlers_own_author_rule():
    both = _row(MessageDirection.OUTBOUND, "x", human=True, auto=True)
    assert roles.author_of(both) == "twin"


def test_markers_echoed_by_the_model_never_reach_the_contact():
    assert roles.strip_author_markers("[Gêmeo] Vou sim.") == "Vou sim."
    assert roles.strip_author_markers("[Dário]  oi\n[Gêmeo] tudo bem") == "oi\ntudo bem"


# ------------------------------------------------------------------------------------------------- prompt: sujeito e outras conversas

def test_persona_prompt_carries_the_role_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_factory, "chat_with_fallback", lambda *a, **k: None, raising=False)
    import agents.darius_twin as dt

    (tmp_path / "darius_twin.md").write_text("PERSONA <!-- comentário -->", encoding="utf-8")
    (tmp_path / "twin_conversation.md").write_text("CONVERSA", encoding="utf-8")
    monkeypatch.setattr(dt, "_PROMPT_PATH", tmp_path / "darius_twin.md")
    monkeypatch.setattr(dt, "_CONVERSATION_PATH", tmp_path / "twin_conversation.md")
    text = dt.load_persona_prompt()
    assert text.startswith("PERSONA\n\nCONVERSA") and text.endswith(roles.ROLE_RULES)
    assert "SOBRE O DÁRIO" in text and "OUTRAS conversas" in text


async def test_contact_line_says_the_contact_is_not_the_owner_and_old_layout_is_kept(twin):
    await twin.module.generate_darius_reply(
        [ChatMessage(role="user", content="oi")], "vai hoje?", contact_name="Paulo", extra_system=["BLOCO DE ESTILO"]
    )
    systems = [m.content for m in twin.calls[0] if m.role == "system"]
    assert systems[0] == "PERSONA" and systems[2] == "BLOCO DE ESTILO"                       # mesma ordem e mesma contagem de antes
    assert systems[1].startswith("Você está respondendo, pelo WhatsApp, para: Paulo.") and "NÃO é o Dário" in systems[1]


def test_style_block_says_examples_are_other_conversations_and_owner_facts_stay_allowed_for_the_twin(monkeypatch):
    monkeypatch.setattr(get_settings(), "evolution_personal_instance", "pessoal")
    twin_block = style_context.format_style_block(["Pergunta: melhorou?\nResposta: " + BUGGY_REPLY], "pessoal")
    assert "OUTRA conversa" in twin_block and "fatos sobre o próprio Dário" in twin_block
    assert style_context.HEADER_RULES in twin_block and "Resposta: " + BUGGY_REPLY in twin_block   # o exemplo e as regras antigas ficam
    store_block = style_context.format_style_block(["Pergunta: a\nResposta: b"], "MARQUESCOLOR")
    assert "OUTRA conversa" in store_block and "próprio Dário" not in store_block                 # a exceção é só do Gêmeo


# --------------------------------------------------------------------------------------------------------------- a resposta final

async def test_regression_libina_health_question_is_not_returned_but_the_owners_own_state_is_kept(twin):
    reply = await twin.module.generate_darius_reply([], "Bom dia, melhorou?", contact_name="Gerente LIBINA")
    assert "Vc tá melhorando aí?" not in reply and "?" not in reply
    assert reply == "Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também."


async def test_negative_control_a_contact_who_says_he_is_sick_may_get_the_question_back(twin):
    history = [ChatMessage(role="user", content="Tô gripado desde segunda")]
    assert await twin.module.generate_darius_reply(history, "E você, melhorou?", contact_name="Paulo") == BUGGY_REPLY
    # dito na própria mensagem pendente
    assert await twin.module.generate_darius_reply([], "Melhorou? Eu também tô com febre", contact_name="Paulo") == BUGGY_REPLY


async def test_owner_fact_from_another_conversation_is_still_used(twin):
    block = style_context.format_style_block([f"Pergunta: Melhorou?\nResposta: {BUGGY_REPLY}"], "pessoal")
    reply = await twin.module.generate_darius_reply([], "Tá melhor hoje?", contact_name="Gerente LIBINA", extra_system=[block])
    assert any(OWNER_FACT in m.content for m in twin.calls[0] if m.role == "system")           # o fato do dono chegou ao modelo
    assert OWNER_FACT in reply                                                                  # e sobreviveu na resposta


async def test_guard_leaves_unrelated_questions_and_other_conversations_alone(twin):
    twin.reply = "Fechado. Qual horário fica bom pra você?"
    assert await twin.module.generate_darius_reply([], "Bom dia, melhorou?", contact_name="X") == twin.reply
    twin.reply = "Tô bem sim. Vc tá melhorando aí?"
    assert await twin.module.generate_darius_reply([], "Oi, preciso do orçamento", contact_name="X") == twin.reply   # ele não perguntou pela saúde


async def test_reply_that_is_only_the_returned_health_question_becomes_unavailable_not_inverted(twin):
    twin.reply = "E você, melhorou?"
    with pytest.raises(twin.module.TwinReplyUnavailable):
        await twin.module.generate_darius_reply([], "Melhorou?", contact_name="X")


async def test_marker_copied_by_the_model_is_stripped_from_the_final_reply(twin):
    twin.reply = "[Dário] Tô na mesma ainda."
    assert await twin.module.generate_darius_reply([], "Melhorou?", contact_name="X") == "Tô na mesma ainda."


@pytest.mark.parametrize("text,expected", [
    ("Bom dia, melhorou?", True), ("Como você tá?", True), ("Melhoras!", True), ("Já passou a febre?", True),
    ("Tá bem?", True), ("Preciso do orçamento", False), ("Que horas abre?", False),
])
def test_what_counts_as_a_question_about_the_owners_health(text, expected):
    assert roles.asks_about_owner_health(text) is expected


@pytest.mark.parametrize("text,expected", [
    ("Tô gripado", True), ("eu também estou doente", True), ("peguei covid", True), ("minha febre não passa", True),
    ("Tô com dor de garganta", True), ("Melhorou?", False), ("Estou ótimo, obrigado", False),
])
def test_what_counts_as_the_interlocutor_saying_he_is_sick(text, expected):
    assert roles.says_they_are_sick([text]) is expected


# ------------------------------------------------------------------------------------- ponta a ponta: o handler real, com banco real

@pytest.fixture
async def world(db_engine, twin, monkeypatch):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    settings = get_settings()
    for name, value in dict(whatsapp_twin_mode_enabled=True, evolution_personal_instance="Dario-nao-esta-em-uso", style_examples_enabled=False,
                            whatsapp_owner_alert_phone="").items():
        monkeypatch.setattr(settings, name, value, raising=False)
    from services import conversation_control

    async def not_paused(db, contact_id, instance):          # a tabela conversation_controls é SQL de Postgres (migration); o controle humano não é o assunto aqui
        return {"paused": False, "revision": 1, "inflight": None}

    monkeypatch.setattr(conversation_control, "snapshot", not_paused)
    import jobs.handlers as handlers

    async def still_current(*args, **kwargs):               # `jobs.owner_audio_dependencies` só existe na produção; áudio do dono não é o assunto
        return True

    monkeypatch.setattr(handlers, "_owner_audio_after_generation", still_current)
    w = SimpleNamespace(sessions=sessions, instance="darioos", llm=twin)
    async with sessions() as db:
        db.add(User(email="dono@example.com", full_name="Dono", hashed_password="x", role=UserRole.ADMIN))
        contact = Contact(name="Gerente LIBINA", phone="5511999990077", preferences={}, awaiting_reply_since=NOW)
        db.add(contact)
        await db.flush()
        rows = [
            (MessageDirection.INBOUND, "Bom dia!", False, False, 50),
            (MessageDirection.OUTBOUND, "Bom dia, tudo certo?", True, False, 40),          # digitado pelo dono
            (MessageDirection.OUTBOUND, "Vou ver isso e te falo.", False, True, 30),       # resposta do próprio Gêmeo
            (MessageDirection.INBOUND, "Bom dia, melhorou?", False, False, 1),             # pendente
        ]
        ids = []
        for direction, content, human, auto, minutes_ago in rows:
            at = NOW - timedelta(minutes=minutes_ago)
            m = Message(contact_id=contact.id, direction=direction, media_type=MessageMediaType.TEXT, content=content,
                        whatsapp_instance=w.instance, sent_by_human=human, is_autopilot_reply=auto, created_at=at, provider_timestamp=at)
            db.add(m)
            await db.flush()
            ids.append(m.id)
        await db.commit()
        w.contact_id, w.pending_id = contact.id, ids[-1]
    return w


async def _run_handler(w):
    from jobs.handlers import twin_autopilot_check

    async with w.sessions() as db:
        await twin_autopilot_check(db, {"contact_id": w.contact_id, "message_id": w.pending_id, "instance": w.instance})


async def _sent_texts(w):
    async with w.sessions() as db:
        jobs = (await db.execute(select(Job).where(Job.name == "whatsapp.send_text"))).scalars().all()
        return [j.payload["content"] for j in jobs]


async def test_end_to_end_libina_case_through_the_real_handler(world):
    await _run_handler(world)
    (sent,) = await _sent_texts(world)
    assert sent == "Ainda não, tô na mesma. Febre não baixou ontem à noite, tá ruim de engolir também."
    history = [m for m in world.llm.calls[0] if m.role in ("user", "assistant")]
    assert [(m.role, m.content) for m in history] == [
        ("user", "Bom dia!"),
        ("assistant", "[Dário] Bom dia, tudo certo?"),
        ("assistant", "[Gêmeo] Vou ver isso e te falo."),
        ("user", "Bom dia, melhorou?"),
    ]


async def test_end_to_end_negative_control_sick_contact_gets_the_question(world):
    async with world.sessions() as db:
        msg = await db.get(Message, world.pending_id)
        msg.content = "Bom dia, melhorou? Eu tô gripado também"
        await db.commit()
    await _run_handler(world)
    assert await _sent_texts(world) == [BUGGY_REPLY]


async def test_kill_switch_turns_off_only_the_health_question_removal(twin, monkeypatch):
    monkeypatch.setattr(get_settings(), "twin_role_guard_enabled", False, raising=False)
    assert await twin.module.generate_darius_reply([], "Bom dia, melhorou?", contact_name="X") == BUGGY_REPLY
    twin.reply = "[Gêmeo] Tô na mesma."
    assert await twin.module.generate_darius_reply([], "Bom dia, melhorou?", contact_name="X") == "Tô na mesma."   # marcador sai sempre
