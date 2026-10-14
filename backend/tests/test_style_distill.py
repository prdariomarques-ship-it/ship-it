"""Aprendizado do estilo do dono: filtros, lote real (SQL real em SQLite), job autorreagendavel, busca e uso no Twin.

Reais: `services/style_distill`, `MemoryManager`, `MemoryService`, SQL, `jobs/style_job`, `agents/darius_twin`.
Substituidos: o cliente do Qdrant e o provedor de embeddings (como em test_catalog_index_handlers.py) e o LLM do Twin.
NAO prova: qualidade da recuperacao com embeddings reais (por isso `style_min_score` nasce em 0.0 e deve ser calibrado com dados
de producao) nem o comportamento no Postgres/Qdrant reais.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import agents.darius_twin_context as twin_context
import jobs.style_job as style_job
import memory.service as memory_service_module
import providers.llm.factory as llm_factory
from memory.service import memory_service
from models.contact import Contact
from models.embedding import Embedding
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from providers.llm.base import ChatMessage
from services import style_distill
from utils.config import get_settings

NOW = datetime.now(timezone.utc)
IN, OUT = MessageDirection.INBOUND, MessageDirection.OUTBOUND
TEXT, AUDIO = MessageMediaType.TEXT, MessageMediaType.AUDIO
SOURCE = "style_example:pessoal"
COMMON = dict(max_chars=400, min_chars=2, excluded=frozenset(), min_audio_words=8, include_financial=False)


def _check(text, **overrides):
    return style_distill.check_text(text, from_audio=overrides.pop("from_audio", False), **{**COMMON, **overrides})


# ---------------------------------------------------------------- filtros puros


@pytest.mark.parametrize(
    "text, reason",
    [
        ("", "vazio"),
        ("Oi! Aqui é o assistente automático do Dário — ele viu sua mensagem e prefiro que ele mesmo te responda", "texto_automatico"),
        ("Aqui é a Chroma, da Oficina das Tintas Ribeirão Pires", "texto_automatico"),
        ("Aqui é o Twin, assistente do Dário.", "texto_automatico"),
        ("k", "curto"),
        ("x" * 401, "longo"),
        ("me manda em dariomneto@hotmail.com", "dado_pessoal_ou_valor"),
        ("olha https://exemplo.com/a", "dado_pessoal_ou_valor"),
        ("meu zap 11 98258-9350", "dado_pessoal_ou_valor"),
        ("fica R$ 150,00 a lata", "dado_pessoal_ou_valor"),
        ("quero morrer", "assunto_de_risco"),
        ("vou vender a empresa", "assunto_de_risco"),
        ("vou investir em tesouro direto", "assunto_de_risco"),
    ],
)
def test_filtros_recusam_o_que_nao_e_estilo_do_dono(text, reason):
    assert _check(text) == reason


@pytest.mark.parametrize("text", ["Vou sim, pode deixar", "Chegou?", "Paz do Senhor, tudo bem?", "kkk tmj"])
def test_texto_normal_de_conversa_passa(text):
    assert _check(text) is None


def test_financeiro_so_entra_se_a_chave_permitir():
    assert _check("vou investir em tesouro direto", include_financial=True) is None
    assert _check("quero morrer", include_financial=True) == "assunto_de_risco"  # crise nunca entra


def test_texto_automatico_exato_configurado_fica_fora():
    excluded = frozenset({style_distill.normalize_text("Olá! Obrigado por entrar em contato.")})
    assert _check("Olá! Obrigado por entrar em contato.", excluded=excluded) == "texto_automatico"
    assert _check("Olá! Obrigado por entrar em contato, Paulo.", excluded=excluded) is None  # so igualdade exata


def test_audio_curto_ou_inventado_e_suspeito_mas_texto_curto_nao():
    assert _check("Devemos outro bem.", from_audio=True) == "audio_suspeito"  # o caso real 11393
    assert _check("Devemos outro bem.", from_audio=False) is None
    assert _check("Legendas pela comunidade Amara.org e mais algumas palavras aqui", from_audio=True) == "audio_suspeito"
    assert _check("sim sim sim sim sim sim sim sim sim sim", from_audio=True) == "audio_suspeito"  # laco repetido
    longo = "então eu vi a sua mensagem agora e vou te responder com calma mais tarde pode ser"
    assert _check(longo, from_audio=True) is None


def test_exemplo_tem_pergunta_e_resposta():
    assert style_distill.build_example(" Chegou? ", " Ainda não. ") == "Pergunta: Chegou?\nResposta: Ainda não."


# ---------------------------------------------------------------- lote com SQL real


@pytest.fixture
async def world(db_engine, monkeypatch):
    client = MagicMock()
    client.upsert, client.delete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(memory_service, "_client", client)
    monkeypatch.setattr(memory_service, "_collection_ready", True)
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)
    monkeypatch.setattr(memory_service_module, "get_embedding_provider", lambda: embedder)
    settings = get_settings()
    monkeypatch.setattr(settings, "evolution_personal_instance", "pessoal")
    monkeypatch.setattr(settings, "style_instances", "")
    monkeypatch.setattr(settings, "style_excluded_texts", "")
    monkeypatch.setattr(settings, "style_distill_enabled", True)
    monkeypatch.setattr(settings, "style_distill_batch_size", 50)

    class W:
        pass

    w = W()
    w.sessions, w.client, w.minute = async_sessionmaker(db_engine, expire_on_commit=False), client, 0
    async with w.sessions() as db:
        contact = Contact(name="Cliente", phone="5511900000001")
        db.add(contact)
        await db.commit()
        w.contact_id = contact.id
    return w


async def _msg(w, direction, content, *, human=False, auto=False, instance="pessoal", media=TEXT):
    w.minute += 1
    async with w.sessions() as db:
        message = Message(
            contact_id=w.contact_id, direction=direction, media_type=media, content=content, whatsapp_instance=instance,
            sent_by_human=human, is_autopilot_reply=auto, created_at=NOW - timedelta(hours=1) + timedelta(minutes=w.minute),
        )
        db.add(message)
        await db.commit()
        return message.id


async def _run(w, **kwargs):
    async with w.sessions() as db:
        return await style_distill.distill_batch(db, **kwargs)


async def _examples(w):
    async with w.sessions() as db:
        return list((await db.execute(select(Embedding).order_by(Embedding.id))).scalars())


async def test_resposta_humana_vira_exemplo_com_chave_e_origem_da_instancia(world):
    await _msg(world, IN, "Chegou a tinta?")
    reply = await _msg(world, OUT, "Ainda não, amanhã cedo.", human=True)
    stats = await _run(world)
    assert (stats.scanned, stats.indexed, stats.last_id) == (1, 1, reply)
    (row,) = await _examples(world)
    assert row.source == SOURCE and row.external_id == f"style:{reply}"
    assert row.content == "Pergunta: Chegou a tinta?\nResposta: Ainda não, amanhã cedo."
    assert world.client.upsert.await_args.kwargs["points"][0].payload["source"] == SOURCE


async def test_so_aprende_do_que_uma_pessoa_escreveu_na_instancia_certa(world):
    await _msg(world, IN, "Pode falar?")
    await _msg(world, OUT, "Posso sim.", human=True, auto=True)  # resposta do robo
    await _msg(world, IN, "E amanhã?")
    await _msg(world, OUT, "Oi! Aqui é o assistente automático do Dário — ele viu sua mensagem", human=True)  # eco gravado como humano (11394)
    await _msg(world, IN, "Valeu")
    await _msg(world, OUT, "Tmj!", human=True, instance="MARQUESCOLOR")  # outra instancia
    stats = await _run(world)
    assert stats.indexed == 0
    assert stats.rejected == {"resposta_texto_automatico": 1}
    assert await _examples(world) == []


async def test_so_a_primeira_resposta_depois_da_pergunta_forma_par(world):
    await _msg(world, IN, "Bom dia, tem como ver isso?")
    await _msg(world, OUT, "Bom dia, vejo sim.", human=True)
    await _msg(world, OUT, "Já te falo.", human=True)  # responde ao proprio dono
    stats = await _run(world)
    assert (stats.indexed, stats.rejected) == (1, {"sem_pergunta_anterior": 1})


async def test_audio_do_cliente_curto_nao_vira_pergunta(world):
    await _msg(world, IN, "Vais para a história.", media=AUDIO)  # transcricao inventada (11392)
    await _msg(world, OUT, "Paz!", human=True)
    stats = await _run(world)
    assert (stats.indexed, stats.rejected) == (0, {"pergunta_audio_suspeito": 1})


async def test_repetir_o_lote_substitui_e_o_cursor_pula_o_ja_visto(world):
    await _msg(world, IN, "Chegou a tinta?")
    first = await _msg(world, OUT, "Ainda não, amanhã cedo.", human=True)
    await _run(world)
    await _run(world)  # mesma janela, sem cursor: substitui, nao duplica
    assert len(await _examples(world)) == 1
    stats = await _run(world, after_id=first)
    assert (stats.scanned, stats.last_id) == (0, first)


async def test_sem_instancia_configurada_nao_aprende_nada(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "evolution_personal_instance", "")
    await _msg(world, IN, "Chegou a tinta?")
    await _msg(world, OUT, "Ainda não.", human=True)
    assert (await _run(world)).scanned == 0


async def test_texto_automatico_da_loja_configurado_fica_fora(world, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "style_instances", "pessoal,MARQUESCOLOR")
    monkeypatch.setattr(settings, "style_excluded_texts", "Olá! Estamos fechados agora. | Obrigado por entrar em contato!")
    await _msg(world, IN, "Boa tarde", instance="MARQUESCOLOR")
    await _msg(world, OUT, "Olá! Estamos fechados agora.", human=True, instance="MARQUESCOLOR")
    await _msg(world, IN, "Tem a Coral branca?", instance="MARQUESCOLOR")
    await _msg(world, OUT, "Tem sim, vem buscar.", human=True, instance="MARQUESCOLOR")
    stats = await _run(world)
    assert (stats.indexed, stats.rejected) == (1, {"resposta_texto_automatico": 1})
    (row,) = await _examples(world)
    assert row.source == "style_example:MARQUESCOLOR"


# ---------------------------------------------------------------- job


async def _jobs(w):
    async with w.sessions() as db:
        return list((await db.execute(select(Job).where(Job.name == style_job.JOB_NAME).order_by(Job.id))).scalars())


async def test_job_processa_e_se_reagenda_com_o_cursor(world):
    await _msg(world, IN, "Chegou a tinta?")
    reply = await _msg(world, OUT, "Ainda não, amanhã cedo.", human=True)
    async with world.sessions() as db:
        await style_job.distill_style_tick(db, {"after_id": 0})
    (next_job,) = await _jobs(world)
    assert next_job.payload == {"after_id": reply}
    assert len(await _examples(world)) == 1


async def test_job_desligado_nao_aprende_mas_mantem_a_corrente_sem_perder_o_cursor(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "style_distill_enabled", False)
    await _msg(world, IN, "Chegou a tinta?")
    await _msg(world, OUT, "Ainda não.", human=True)
    async with world.sessions() as db:
        await style_job.distill_style_tick(db, {"after_id": 7})
    assert await _examples(world) == []
    assert (await _jobs(world))[0].payload == {"after_id": 7}


async def test_semente_so_existe_com_a_chave_ligada_e_nao_duplica_a_corrente(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "style_distill_enabled", False)
    async with world.sessions() as db:
        await style_job.start(db)
    assert await _jobs(world) == []
    monkeypatch.setattr(get_settings(), "style_distill_enabled", True)
    async with world.sessions() as db:
        await style_job.start(db)
        await style_job.start(db)
    assert len(await _jobs(world)) == 1


# ---------------------------------------------------------------- busca e uso no Twin


def _qdrant_points(world, *items):
    points = [SimpleNamespace(payload={"content": text, "source": SOURCE}, score=score) for text, score in items]
    world.client.query_points = AsyncMock(return_value=SimpleNamespace(points=points))


async def test_busca_usa_so_a_origem_da_instancia_e_respeita_o_limiar(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "style_min_score", 0.5)
    _qdrant_points(world, ("Pergunta: a\nResposta: b", 0.9), ("Pergunta: c\nResposta: d", 0.2))
    assert await style_distill.retrieve_style_examples("chegou?", "pessoal") == ["Pergunta: a\nResposta: b"]
    condition = world.client.query_points.await_args.kwargs["query_filter"].must[0]
    assert (condition.key, condition.match.value) == ("source", SOURCE)
    assert await style_distill.retrieve_style_examples("", "pessoal") == []
    assert await style_distill.retrieve_style_examples("chegou?", "") == []


async def test_bloco_do_twin_so_existe_com_a_chave_ligada(world, monkeypatch):
    _qdrant_points(world, ("Pergunta: Chegou?\nResposta: Ainda não.", 0.9))
    monkeypatch.setattr(get_settings(), "style_examples_enabled", False)
    assert await twin_context.build_twin_extra_system("chegou?", "pessoal") == []
    monkeypatch.setattr(get_settings(), "style_examples_enabled", True)
    (block,) = await twin_context.build_twin_extra_system("chegou?", "pessoal")
    assert block.startswith(twin_context.STYLE_HEADER) and "Exemplo 1:\nPergunta: Chegou?\nResposta: Ainda não." in block
    assert "não são fatos" in block or "não fatos" in block or "São exemplos, não fatos" in block


async def test_falha_na_busca_de_estilo_nao_impede_o_twin(world, monkeypatch):
    monkeypatch.setattr(get_settings(), "style_examples_enabled", True)
    world.client.query_points = AsyncMock(side_effect=RuntimeError("qdrant fora"))
    assert await twin_context.build_twin_extra_system("chegou?", "pessoal") == []


async def test_twin_recebe_os_blocos_extras_como_mensagens_de_sistema(monkeypatch):
    captured = {}

    async def fake_chat(messages, tools=None):
        captured["messages"] = messages
        return SimpleNamespace(content="Vou sim.")

    # `chat_with_fallback` (Qwen -> DeepSeek) so existe na fabrica de LLM de PRODUCAO; a candidata ainda nao a tem. Por isso o simbolo e
    # injetado ANTES de importar o modulo copiado da producao (agents/darius_twin.py, sha256 c935113114ac5a71 + `extra_system`).
    monkeypatch.setattr(llm_factory, "chat_with_fallback", fake_chat, raising=False)
    import agents.darius_twin as darius_twin

    monkeypatch.setattr(darius_twin, "chat_with_fallback", fake_chat)
    monkeypatch.setattr(darius_twin, "load_persona_prompt", lambda: "PERSONA")  # os .md do manual so existem na producao
    reply = await darius_twin.generate_darius_reply(
        [ChatMessage(role="user", content="oi")], "vai hoje?", contact_name="Paulo", extra_system=["BLOCO DE ESTILO"]
    )
    assert reply == "Vou sim."
    systems = [m.content for m in captured["messages"] if m.role == "system"]
    assert systems[0] == "PERSONA" and systems[1].startswith("Você está respondendo") and systems[2] == "BLOCO DE ESTILO"
    assert captured["messages"][-1].content == "vai hoje?"
    # sem extra_system o comportamento anterior e identico
    await darius_twin.generate_darius_reply([], "vai hoje?", contact_name="Paulo")
    assert [m.role for m in captured["messages"]].count("system") == 2
