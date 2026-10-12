"""Acompanhamentos comerciais da loja (retomada de orçamento, reposição) — banco isolado, worker real, transporte falso.

Relógio controlado: NOW = terça-feira (06/10/2026) 10:00 em São Paulo (13:00 UTC), dentro da janela 9–18 h, segunda a sábado.
Dados fictícios. Nenhum preço, desconto ou prazo aparece em texto algum.
"""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

import jobs.handlers  # noqa: F401
from jobs.worker import JobWorker
from models.contact import Contact
from models.job import Job
from models.message import Message, MessageDirection, MessageMediaType
from models.product import Product
from models.store import StoreCustomer, StoreQuote
from models.store_aftercare import StoreSupportCase
from models.store_followup import StoreFollowup
from models.store_voice import StoreVoiceSend
from providers.whatsapp.base import WhatsAppProviderError
from services import conversation_control, store_followups as sf, voice_client
from tests.test_store_voice import FakeSynth, TextTransport, VoiceTransport
from tests.test_whatsapp_send_queue_retry import _migrate_control_tables_sync
from utils.config import get_settings

NOW = datetime(2026, 10, 6, 13, 0, tzinfo=timezone.utc)          # terça 10:00 BRT (06/10/2026, no passado do relógio real: o worker real considera os jobs vencidos)
PHONE = "5511999990000"
STORE = "MARQUESCOLOR"


@pytest_asyncio.fixture
async def env(db_engine, monkeypatch):
    async with db_engine.begin() as conn:
        await conn.run_sync(_migrate_control_tables_sync)
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("jobs.worker.async_session_factory", sessions)
    s = get_settings()
    for k, v in dict(
        store_followups_enabled=True, store_whatsapp_enabled=True, auto_reply_enabled=True, evolution_instance=STORE,
        evolution_personal_instance="pessoal-teste", jobs_retry_backoff_seconds=0, store_voice_enabled=False,
        store_timezone="America/Sao_Paulo", store_followup_close_margin_minutes=30,
        store_hours='{"mon-fri": ["08:30", "17:30"], "sat": ["08:30", "12:30"], "holiday": ["08:30", "12:30"]}',
        store_extra_holidays="", store_excluded_holidays="", store_followup_quote_resume_delay_minutes=120, store_followup_max_age_days=7,
        store_followup_max_attempts=1, store_followup_min_gap_hours=72, store_followup_restock_min_orders=3,
        store_followup_restock_tolerance=0.25,
    ).items():
        monkeypatch.setattr(s, k, v)
    text_t, voice_t, synth = TextTransport(), VoiceTransport(), FakeSynth()
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: text_t)
    monkeypatch.setattr("services.store_voice.get_whatsapp_provider", lambda: voice_t)
    monkeypatch.setattr(voice_client, "synthesize", synth)

    class Env:
        pass
    e = Env()
    e.sessions, e.text, e.voice, e.synth, e.s = sessions, text_t, voice_t, synth, s
    return e


async def add_products(env):
    async with env.sessions() as db:
        db.add_all([
            Product(sku="TL18", name="Tinta Látex Branca 18L", unit="lata_18L", unit_price=Decimal("450.00"), stock_quantity=10, active=True),
            Product(sku="ROLO", name="Rolo de Lã 23cm", unit="un", unit_price=Decimal("25.00"), stock_quantity=0, active=True),
            Product(sku="VERN", name="Verniz Marítimo 3,6L", unit="galao", unit_price=Decimal("120.00"), stock_quantity=5, active=False),
        ])
        await db.commit()


async def add_customer(env, *, phone=PHONE, name="Marina Souza", orders=None, instance_history=STORE, prefs=None):
    """Cliente + contato + (opcional) uma mensagem recebida na instância dada. Devolve (customer_id, contact_id)."""
    async with env.sessions() as db:
        contact = Contact(name=name, phone=phone, preferences=prefs or {})
        customer = StoreCustomer(name=name, phone=phone, orders=orders or [])
        db.add_all([contact, customer])
        await db.flush()
        if instance_history:
            db.add(Message(contact_id=contact.id, direction=MessageDirection.INBOUND, media_type=MessageMediaType.TEXT, content="Oi, preciso de tinta",
                           whatsapp_instance=instance_history, created_at=NOW - timedelta(days=3)))
        await db.commit()
        return customer.id, contact.id


def line(sku="TL18", name="Tinta Látex Branca 18L", qty=2, price="450.00"):
    return dict(sku=sku, name=name, unit="lata_18L", quantity=qty, unit_price=price, line_total=str(Decimal(price) * qty))


async def add_quote(env, customer_id, contact_id, *, qid="ABC123DEF456", created=None, items=None, confirmed=None):
    created = created or NOW - timedelta(hours=5)
    async with env.sessions() as db:
        db.add(StoreQuote(id=qid, contact_id=contact_id, customer_id=customer_id, items=items or [line()], total=Decimal("900.00"),
                          expires_at=created + timedelta(minutes=30), confirmed_at=confirmed, created_at=created))
        await db.commit()
    return qid


async def all_followups(env):
    async with env.sessions() as db:
        return list((await db.scalars(select(StoreFollowup).order_by(StoreFollowup.id))).all())


async def plan(env, **kw):
    async with env.sessions() as db:
        return await sf.plan_quote_resumes(db, now=kw.pop("now", NOW), **kw)


async def run(env, **kw):
    async with env.sessions() as db:
        return await sf.run_due(db, now=kw.pop("now", NOW), **kw)


async def scenario(env, **cust):
    await add_products(env)
    cid, kid = await add_customer(env, **cust)
    qid = await add_quote(env, cid, kid)
    return cid, kid, qid


# ----------------------------------------------------------------------------------------------- janela
@pytest.mark.parametrize("utc, dentro", [
    (datetime(2026, 10, 6, 13, 0, tzinfo=timezone.utc), True),      # terça 10:00
    (datetime(2026, 10, 6, 11, 29, tzinfo=timezone.utc), False),    # terça 08:29 (antes de abrir 08:30)
    (datetime(2026, 10, 6, 11, 30, tzinfo=timezone.utc), True),     # 08:30 exato
    (datetime(2026, 10, 6, 19, 59, tzinfo=timezone.utc), True),     # 16:59 (fecha 17:30, margem de 30 min)
    (datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc), False),     # 17:00: dentro da margem final
    (datetime(2026, 10, 10, 14, 59, tzinfo=timezone.utc), True),    # sábado 11:59 (fecha 12:30, margem 30 min)
    (datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc), False),    # sábado 12:00
    (datetime(2026, 10, 10, 18, 0, tzinfo=timezone.utc), False),    # sábado à tarde
    (datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc), False),    # domingo: sem atendimento informado
    (datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc), True),     # segunda 12/10 = feriado (N. Sra. Aparecida): 10:00 dentro de 08:30–12:30
    (datetime(2026, 10, 12, 16, 0, tzinfo=timezone.utc), False),    # feriado 13:00: fora (e dia útil estaria aberto)
])
def test_janela_de_horario(env, utc, dentro):
    assert sf.in_window(utc, env.s) is dentro


def test_proxima_janela_pula_noite_domingo_e_respeita_feriado(env):
    assert sf.next_window(datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc), env.s) == datetime(2026, 10, 7, 11, 30, tzinfo=timezone.utc)   # terça 19h -> quarta 08:30
    assert sf.next_window(datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc), env.s) == datetime(2026, 10, 12, 11, 30, tzinfo=timezone.utc)  # domingo -> segunda (feriado) 08:30
    assert sf.next_window(datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc), env.s) == datetime(2026, 10, 12, 11, 30, tzinfo=timezone.utc)  # sábado 13h -> segunda 08:30
    assert sf.next_window(NOW, env.s) == NOW


# ----------------------------------------------------------------------------------------------- planejamento
async def test_simulacao_nao_grava_nada_e_aplicar_cria_com_todos_os_campos(env):
    cid, kid, qid = await scenario(env)
    dry = await plan(env)
    assert [(e["origin"], e["action"]) for e in dry] == [(qid, "plan")] and await all_followups(env) == []
    applied = await plan(env, apply=True)
    assert applied[0]["action"] == "created"
    (fu,) = await all_followups(env)
    assert (fu.kind, fu.status, fu.attempts, fu.max_attempts, fu.instance) == ("quote_resume", "scheduled", 0, 1, STORE)
    assert (fu.customer_id, fu.contact_id, fu.origin_type, fu.origin_id) == (cid, kid, "store_quote", qid)
    assert fu.dedupe_key == f"quote_resume:{qid}" and fu.reason and fu.cancel_reason is None and fu.history[0]["event"] == "scheduled"
    assert fu.snapshot["quote_id"] == qid and fu.due_at.replace(tzinfo=timezone.utc) == NOW
    again = await plan(env, apply=True)                     # idempotente: mesma chave de deduplicação
    assert again[0]["action"] == "exists" and len(await all_followups(env)) == 1


async def test_orcamento_ainda_nao_vencido_ou_velho_demais_nao_entra(env):
    await add_products(env)
    cid, kid = await add_customer(env)
    await add_quote(env, cid, kid, qid="NOVO00000001", created=NOW - timedelta(minutes=45))             # vence em 0 min; +2h de espera ainda não passou
    await add_quote(env, cid, kid, qid="VELHO0000001", created=NOW - timedelta(days=9))                 # além de 7 dias
    assert [e["origin"] for e in await plan(env)] == []


@pytest.mark.parametrize("nome, setup, motivo", [
    ("opt_out", dict(prefs={"store_contact_opt_out": True}), "não receber"),
    ("opt_out_pos_venda_existente", dict(prefs={"store_followup_opt_out": True}), "não receber"),
    ("recusa_recente", dict(prefs={"store_followup_paused_until": (NOW + timedelta(days=5)).isoformat()}), "recusou"),
    ("sem_conversa_na_loja", dict(instance_history="b2b-sales"), "sem conversa na instância da loja"),
    ("so_instancia_pessoal", dict(instance_history="pessoal-teste"), "sem conversa na instância da loja"),
])
async def test_planejamento_respeita_bloqueios_do_cliente(env, nome, setup, motivo):
    await add_products(env)
    cid, kid = await add_customer(env, **setup)
    await add_quote(env, cid, kid)
    (entry,) = await plan(env)
    assert entry["action"] == "skip" and motivo in entry["reason"]


async def test_telefone_do_cadastro_diferente_do_contato_nao_identifica(env):
    await add_products(env)
    cid, kid = await add_customer(env)
    async with env.sessions() as db:
        (await db.get(StoreCustomer, cid)).phone = "5511888880000"
        await db.commit()
    await add_quote(env, cid, kid)
    (entry,) = await plan(env)
    assert entry["action"] == "skip" and "identificação" in entry["reason"]


async def _msg(env, kid, direction, *, when, human=False, instance=STORE, content="x"):
    async with env.sessions() as db:
        db.add(Message(contact_id=kid, direction=direction, media_type=MessageMediaType.TEXT, content=content, whatsapp_instance=instance,
                       sent_by_human=human, created_at=when))
        await db.commit()


async def test_humano_na_conversa_ou_cliente_que_voltou_a_falar_ou_pausa_ou_reclamacao(env):
    await add_products(env)
    cases = {}
    for tag in ("humano", "voltou", "pausa", "reclamacao", "pedido"):
        phone = {"humano": "5511911110001", "voltou": "5511911110002", "pausa": "5511911110003", "reclamacao": "5511911110004", "pedido": "5511911110005"}[tag]
        cid, kid = await add_customer(env, phone=phone, name=f"Cliente {tag}")
        cases[tag] = (cid, kid, await add_quote(env, cid, kid, qid=f"Q{tag.upper():0<11}"[:12]))
    await _msg(env, cases["humano"][1], MessageDirection.OUTBOUND, when=NOW - timedelta(hours=4), human=True)
    await _msg(env, cases["voltou"][1], MessageDirection.INBOUND, when=NOW - timedelta(hours=3))
    async with env.sessions() as db:
        await conversation_control.pause(db, cases["pausa"][1], STORE, "ev-1", "teste")
        db.add(StoreSupportCase(id="CASO00000001", contact_id=cases["reclamacao"][1], subject="Cor errada", report="x", status="open"))
        c = await db.get(StoreCustomer, cases["pedido"][0])
        c.orders = [{"id": cases["pedido"][2], "items": [line()], "total": "900.00", "created_at": (NOW - timedelta(hours=1)).isoformat()}]
        await db.commit()
    got = {e["origin"]: e["reason"] for e in await plan(env)}
    assert "humano" in got[cases["humano"][2]] and "voltou a falar" in got[cases["voltou"][2]] and "pausada" in got[cases["pausa"][2]]
    assert "reclamação" in got[cases["reclamacao"][2]] and "virou pedido" in got[cases["pedido"][2]]


async def test_quote_confirmada_nunca_e_retomada(env):
    await add_products(env)
    cid, kid = await add_customer(env)
    await add_quote(env, cid, kid, confirmed=NOW - timedelta(hours=4))
    assert await plan(env) == []


# ----------------------------------------------------------------------------------------------- execução
async def planned(env):
    cid, kid, qid = await scenario(env)
    await plan(env, apply=True)
    return cid, kid, qid


async def test_aplicar_desligado_e_recusado_mas_simulacao_funciona(env, monkeypatch):
    await planned(env)
    monkeypatch.setattr(env.s, "store_followups_enabled", False)
    with pytest.raises(sf.FollowupsDisabled):
        await run(env, apply=True)
    (entry,) = await run(env)
    assert entry["action"] == "dry_run" and (await all_followups(env))[0].status == "scheduled"


async def test_texto_so_tem_fatos_verificaveis_sem_preco_desconto_ou_prazo(env):
    cid, kid, qid = await planned(env)
    (entry,) = await run(env)
    body = entry["text"]
    assert qid in body and "2 × Tinta Látex Branca 18L" in body and body.endswith("Para não receber mais contatos automáticos, responda PARAR.")
    assert body.startswith("Olá, Marina! Aqui é o assistente virtual da MARQUESCOLOR.")
    assert not re.search(r"R\$|450|900|desconto|promo|prazo|entrega em|frete|garant", body, re.I)


async def test_nome_so_quando_confiavel(env):
    assert sf.first_name(StoreCustomer(name="  ", phone="1")) is None
    assert sf.first_name(StoreCustomer(name="5511999990000", phone="1")) is None
    assert sf.first_name(StoreCustomer(name="J. Silva", phone="1")) is None
    assert sf.first_name(StoreCustomer(name="MARINA souza", phone="1")) == "Marina"


async def test_aplicar_enfileira_uma_vez_pela_instancia_da_loja(env):
    cid, kid, qid = await planned(env)
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "queued"
    (fu,) = await all_followups(env)
    assert fu.status == "queued" and fu.attempts == 1 and fu.job_id == entry["job_id"] and fu.history[-1]["event"] == "queued"
    async with env.sessions() as db:
        job = await db.get(Job, fu.job_id)
        assert job.name == "whatsapp.send_text" and job.payload["instance"] == STORE and job.payload["to"] == PHONE and job.payload["followup_id"] == fu.id
    assert await run(env, apply=True) == []                  # não está mais 'scheduled': nada a reenfileirar
    assert len(env.text.calls) == 0                          # nada foi transmitido ainda (só a fila)


async def test_ciclo_completo_pelo_worker_real_e_conciliacao(env):
    await planned(env)
    await run(env, apply=True)
    for _ in range(3):
        await JobWorker().run_once()
    assert len(env.text.calls) == 1 and env.text.calls[0][0] == PHONE
    async with env.sessions() as db:
        counts = await sf.reconcile(db)
    assert counts == {"sent": 1, "needs_review": 0, "cancelled": 0}
    (fu,) = await all_followups(env)
    assert fu.status == "sent" and fu.sent_at is not None and [h["event"] for h in fu.history] == ["scheduled", "queued", "sent"]


async def test_resultado_incerto_do_transporte_nao_reenvia_e_vai_para_revisao(env, monkeypatch):
    calls = []

    class Flaky(TextTransport):
        async def send_text(self, to, content, instance=None):
            calls.append(content)
            e = WhatsAppProviderError("evolution request failed: ReadTimeout")
            e.__cause__ = httpx.ReadTimeout("sem resposta")
            raise e
    monkeypatch.setattr("jobs.handlers.get_whatsapp_provider", lambda: Flaky())
    await planned(env)
    await run(env, apply=True)
    for _ in range(6):
        await JobWorker().run_once()
    assert len(calls) == 1                                   # a fila tentou uma única vez (reserva por job)
    async with env.sessions() as db:
        counts = await sf.reconcile(db)
    assert counts["needs_review"] == 1
    (fu,) = await all_followups(env)
    assert fu.status == "needs_review" and "não reenviado" in fu.history[-1]["detail"]
    assert await run(env, apply=True) == []                  # nem um novo envio é criado


async def test_pausa_depois_do_enfileiramento_suprime_o_envio_e_a_conciliacao_registra(env):
    cid, kid, qid = await planned(env)
    await run(env, apply=True)
    async with env.sessions() as db:
        await conversation_control.pause(db, kid, STORE, "ev-9", "humano assumiu")
        await db.commit()
    for _ in range(3):
        await JobWorker().run_once()
    assert env.text.calls == []
    async with env.sessions() as db:
        assert (await sf.reconcile(db))["cancelled"] == 1


async def test_conciliacao_de_queued_sem_job(env):
    cid, kid, qid = await planned(env)
    async with env.sessions() as db:
        fu = (await db.scalars(select(StoreFollowup))).one()
        fu.status, fu.updated_at = "queued", NOW - timedelta(hours=1)
        await db.commit()
    async with env.sessions() as db:
        await sf.reconcile(db)
    assert (await all_followups(env))[0].status == "needs_review"


# --- reconferência NA HORA do envio ------------------------------------------------------------------
async def _change(env, fn):
    async with env.sessions() as db:
        await fn(db)
        await db.commit()


@pytest.mark.parametrize("nome, mutation, motivo", [
    ("opt_out", lambda cid, kid: ("contact", kid, lambda c: setattr(c, "preferences", {"store_contact_opt_out": True})), "não receber"),
    ("recusa", lambda cid, kid: ("contact", kid, lambda c: setattr(c, "preferences", {"store_followup_paused_until": (NOW + timedelta(days=9)).isoformat()})), "recusou"),
    ("telefone_mudou", lambda cid, kid: ("customer", cid, lambda c: setattr(c, "phone", "5511777770000")), "identificação"),
])
async def test_reconferencia_cancela_com_motivo_registrado(env, nome, mutation, motivo):
    cid, kid, qid = await planned(env)
    kind, ident, fn = mutation(cid, kid)

    async def apply_change(db):
        fn(await db.get(Contact if kind == "contact" else StoreCustomer, ident))
    await _change(env, apply_change)
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "cancel" and motivo in entry["reason"]
    (fu,) = await all_followups(env)
    assert fu.status == "cancelled" and motivo in fu.cancel_reason and fu.history[-1]["event"] == "cancelled" and fu.job_id is None
    async with env.sessions() as db:
        assert (await db.scalars(select(Job).where(Job.name == "whatsapp.send_text"))).first() is None


async def test_reconferencia_cliente_escreveu_humano_assumiu_estoque_e_confirmacao(env):
    for tag in ("escreveu", "humano", "estoque", "confirmou"):
        env_phone = {"escreveu": "5511922220001", "humano": "5511922220002", "estoque": "5511922220003", "confirmou": "5511922220004"}[tag]
        await add_products(env) if tag == "escreveu" else None
        cid, kid = await add_customer(env, phone=env_phone, name=f"Cliente {tag}")
        await add_quote(env, cid, kid, qid=f"R{tag.upper():0<11}"[:12], items=[line("ROLO", "Rolo de Lã 23cm", 1, "25.00")] if tag == "estoque" else None)
    await plan(env, apply=True)
    fus = {f.contact_id: f for f in await all_followups(env)}
    assert len(fus) == 4
    by_phone = {}
    async with env.sessions() as db:
        for c in (await db.scalars(select(Contact))).all():
            by_phone[c.phone] = c.id
    await _msg(env, by_phone["5511922220001"], MessageDirection.INBOUND, when=NOW - timedelta(minutes=30), content="vou querer sim")
    await _msg(env, by_phone["5511922220002"], MessageDirection.OUTBOUND, when=NOW - timedelta(minutes=20), human=True)
    async with env.sessions() as db:
        await db.execute(update(StoreQuote).where(StoreQuote.id == "RCONFIRMOU00").values(confirmed_at=NOW - timedelta(minutes=10)))
        await db.commit()
    report = {r["followup_id"]: r for r in await run(env, apply=True)}
    reasons = {fus[by_phone[p]].dedupe_key.split(":")[1][1:5]: report[fus[by_phone[p]].id]["reason"] for p in by_phone}
    assert "voltou a falar" in reasons["ESCR"] and "humano" in reasons["HUMA"]
    assert "disponível" in reasons["ESTO"] and "confirmado" in reasons["CONF"]
    assert all(r["action"] == "cancel" for r in report.values()) and env.text.calls == []


async def test_item_sem_estoque_sai_do_texto_e_sem_nenhum_item_cancela(env):
    await add_products(env)
    cid, kid = await add_customer(env)
    await add_quote(env, cid, kid, items=[line("TL18", "Tinta Látex Branca 18L", 2), line("ROLO", "Rolo de Lã 23cm", 1, "25.00"),
                                          line("VERN", "Verniz Marítimo 3,6L", 1, "120.00")])
    await plan(env, apply=True)
    (entry,) = await run(env)
    assert "2 × Tinta Látex Branca 18L" in entry["text"] and "Rolo" not in entry["text"] and "Verniz" not in entry["text"]


async def test_fora_da_janela_adia_sem_gastar_tentativa(env):
    await planned(env)
    night = datetime(2026, 10, 6, 22, 30, tzinfo=timezone.utc)          # 19:30 BRT
    (entry,) = await run(env, apply=True, now=night)
    assert entry["action"] == "defer"
    (fu,) = await all_followups(env)
    assert fu.status == "scheduled" and fu.attempts == 0 and fu.due_at.replace(tzinfo=timezone.utc) == datetime(2026, 10, 7, 11, 30, tzinfo=timezone.utc)
    assert fu.history[-1]["event"] == "deferred"


async def test_limite_de_tentativas_esgota(env):
    await planned(env)
    async with env.sessions() as db:
        fu = (await db.scalars(select(StoreFollowup))).one()
        fu.attempts = fu.max_attempts
        await db.commit()
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "exhausted" and (await all_followups(env))[0].status == "exhausted"


async def test_intervalo_minimo_entre_contatos_proativos(env):
    cid, kid, qid = await planned(env)
    async with env.sessions() as db:
        db.add(StoreFollowup(dedupe_key="restock:x", kind="restock", contact_id=kid, customer_id=cid, instance=STORE, origin_type="o", origin_id="o",
                             reason="r", due_at=NOW, status="sent", sent_at=NOW - timedelta(hours=10), updated_at=NOW - timedelta(hours=10), history=[], snapshot={}))
        await db.commit()
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "cancel" and "recente" in entry["reason"]


async def test_instancia_pessoal_ou_forjada_nunca_envia(env):
    cid, kid, qid = await planned(env)
    async with env.sessions() as db:
        (await db.scalars(select(StoreFollowup))).one().instance = "pessoal-teste"
        await db.commit()
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "cancel" and "instância" in entry["reason"] and env.text.calls == []


# --- voz nos acompanhamentos -------------------------------------------------------------------------
async def test_voz_no_acompanhamento_so_se_o_cliente_pediu_audio(env, monkeypatch):
    monkeypatch.setattr(env.s, "store_voice_enabled", True)
    monkeypatch.setattr(env.s, "store_voice_url", "http://voice.test")
    monkeypatch.setattr(env.s, "store_voice_token", "t" * 40)
    await add_products(env)
    plain_c, plain_k = await add_customer(env, phone="5511933330001", name="Sem Preferência")
    audio_c, audio_k = await add_customer(env, phone="5511933330002", name="Pediu Áudio", prefs={"reply_mode": "audio"})
    await add_quote(env, plain_c, plain_k, qid="PLAIN0000001")
    await add_quote(env, audio_c, audio_k, qid="AUDIO0000001")
    await plan(env, apply=True)
    await run(env, apply=True)
    for _ in range(8):
        await JobWorker().run_once()
    assert len(env.text.calls) == 2                          # o texto vai para os dois
    async with env.sessions() as db:
        voices = (await db.scalars(select(StoreVoiceSend))).all()
    assert len(voices) == 1 and voices[0].kind == "followup" and voices[0].contact_id == audio_k and voices[0].status == "sent"
    assert len(env.voice.calls) == 1 and env.voice.calls[0][0] == PHONE.replace("0000", "0000")[:0] + "5511933330002"
    assert not any(ch.isdigit() for ch in voices[0].script_text) and "orçamento" not in voices[0].script_text.lower()


async def test_voz_de_acompanhamento_e_cancelada_se_o_cliente_responde(env, monkeypatch):
    monkeypatch.setattr(env.s, "store_voice_enabled", True)
    monkeypatch.setattr(env.s, "store_voice_url", "http://voice.test")
    monkeypatch.setattr(env.s, "store_voice_token", "t" * 40)
    await add_products(env)
    cid, kid = await add_customer(env, prefs={"reply_mode": "audio"})
    await add_quote(env, cid, kid)
    await plan(env, apply=True)
    await run(env, apply=True)

    async def customer_replies():
        await _msg(env, kid, MessageDirection.INBOUND, when=datetime.now(timezone.utc) + timedelta(seconds=1), content="pode refazer")
    env.synth.before = customer_replies
    for _ in range(8):
        await JobWorker().run_once()
    async with env.sessions() as db:
        (v,) = (await db.scalars(select(StoreVoiceSend))).all()
    assert v.status == "cancelled" and "cliente respondeu" in v.reason and env.voice.calls == []


# ----------------------------------------------------------------------------------------------- reposição
def _orders(*days_ago, sku="TL18", qty=2, now=NOW, status=None):
    out = []
    for i, d in enumerate(days_ago):
        o = {"id": f"P{i}", "items": [dict(sku=sku, name="x", quantity=qty, unit_price="1.00", line_total="1.00")], "total": "1.00",
             "created_at": (now - timedelta(days=d)).isoformat()}
        if status:
            o["status"] = status
        out.append(o)
    return out


def _cust(orders):
    return StoreCustomer(name="Marina Souza", phone=PHONE, orders=orders)


def test_ciclo_regular_gera_candidato_somente_na_hora_certa(env):
    # compras há 90, 60 e 30 dias: ciclo de 30 dias; hoje = 30 dias desde a última -> hora de repor
    (c,) = sf.restock_candidates(_cust(_orders(90, 60, 30)), NOW, env.s)
    assert c["sku"] == "TL18" and c["avg_days"] == 30 and c["days_since"] == 30 and c["orders"] == 3 and c["last_quantity"] == 2
    assert sf.restock_candidates(_cust(_orders(90, 60, 10)), NOW, env.s) == []     # cedo demais (10 dias de ciclo de 30)
    assert sf.restock_candidates(_cust(_orders(300, 270, 240)), NOW, env.s) == []  # tarde demais: o ciclo se perdeu (>3x)
    assert len(sf.restock_candidates(_cust(_orders(83, 53, 23)), NOW, env.s)) == 1  # dentro da tolerância de 25% (ciclo 30 -> 22,5)
    assert sf.restock_candidates(_cust(_orders(83, 53, 22)), NOW, env.s) == []     # um dia antes do limite: ainda cedo


@pytest.mark.parametrize("orders", [
    _orders(60, 30), _orders(100, 40, 30), _orders(14, 7, 0), _orders(60, 60, 30),
    _orders(90, 60, 30, status="cancelled"), [{"id": "x", "created_at": "lixo", "items": []}], [], None,
])
def test_sem_historico_confiavel_nao_ha_sugestao(env, orders):
    assert sf.restock_candidates(_cust(orders), NOW, env.s) == []


def test_compras_no_mesmo_pedido_nao_duplicam_e_cancelados_nao_contam(env):
    orders = _orders(90, 60, 30)
    orders[2]["items"].append(dict(sku="TL18", name="x", quantity=1, unit_price="1.00", line_total="1.00"))
    (c,) = sf.restock_candidates(_cust(orders), NOW, env.s)
    assert c["last_quantity"] == 3
    orders.append({**_orders(0)[0], "id": "cancelado", "status": "cancelled"})
    assert len(sf.restock_candidates(_cust(orders), NOW, env.s)) == 1


async def test_reposicao_planeja_texto_so_com_historico_real(env):
    await add_products(env)
    cid, kid = await add_customer(env, orders=_orders(90, 60, 30))
    async with env.sessions() as db:
        (entry,) = await sf.plan_restocks(db, now=NOW)
    assert entry["action"] == "plan" and entry["candidate"]["avg_days"] == 30
    async with env.sessions() as db:
        await sf.plan_restocks(db, now=NOW, apply=True)
    (fu,) = await all_followups(env)
    assert fu.kind == "restock" and fu.dedupe_key == f"restock:{cid}:TL18:{(NOW - timedelta(days=30)).date().isoformat()}"
    (r,) = await run(env)
    assert "Tinta Látex Branca 18L" in r["text"] and "há 30 dias" in r["text"] and "cerca de 30 dias" in r["text"]
    assert not re.search(r"R\$|desconto|promo|prazo|frete", r["text"], re.I) and r["text"].endswith("responda PARAR.")


async def test_reposicao_nao_planeja_produto_sem_estoque_ou_inativo_ou_cliente_ja_recomprou(env):
    await add_products(env)
    await add_customer(env, phone="5511944440001", name="Rolo Sem Estoque", orders=_orders(90, 60, 30, sku="ROLO", qty=1))
    await add_customer(env, phone="5511944440002", name="Verniz Inativo", orders=_orders(90, 60, 30, sku="VERN", qty=1))
    async with env.sessions() as db:
        report = await sf.plan_restocks(db, now=NOW)
    assert {e["action"] for e in report} == {"skip"} and all("produto inativo ou sem estoque" in e["reason"] for e in report)


async def test_reposicao_cancela_na_hora_se_o_cliente_recomprou(env):
    await add_products(env)
    cid, kid = await add_customer(env, orders=_orders(90, 60, 30))
    async with env.sessions() as db:
        await sf.plan_restocks(db, now=NOW, apply=True)
        c = await db.get(StoreCustomer, cid)
        c.orders = [*c.orders, {"id": "NOVO", "items": [dict(sku="TL18", name="x", quantity=2, unit_price="1", line_total="2")], "total": "2",
                                "created_at": (NOW - timedelta(hours=2)).isoformat()}]
        await db.commit()
    (entry,) = await run(env, apply=True)
    assert entry["action"] == "cancel" and "recomprou" in entry["reason"]


async def test_reposicao_nao_incomoda_conversa_ativa_nas_ultimas_48h(env):
    await add_products(env)
    cid, kid = await add_customer(env, orders=_orders(90, 60, 30))
    async with env.sessions() as db:
        assert [e["action"] for e in await sf.plan_restocks(db, now=NOW)] == ["plan"]       # sem conversa recente: entra
    await _msg(env, kid, MessageDirection.INBOUND, when=NOW - timedelta(hours=10), content="bom dia, ainda tem aquela tinta?")
    async with env.sessions() as db:
        (entry,) = await sf.plan_restocks(db, now=NOW)
    assert entry["action"] == "skip" and "conversa ativa" in entry["reason"]
    await _msg(env, kid, MessageDirection.OUTBOUND, when=NOW - timedelta(hours=50), content="y")     # fora das 48h não conta
