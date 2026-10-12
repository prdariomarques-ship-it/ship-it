"""Acompanhamentos comerciais proativos da LOJA: retomada de orçamento vencido e sugestão de reposição.

Garantias (cada uma com teste em tests/test_store_followups.py):
- nada roda sozinho: não há agendador. `plan_*` e `run_due` são chamados por um operador (scripts/store_followups.py), com
  SIMULAÇÃO por padrão; aplicar exige `store_followups_enabled=true`;
- só fatos verificáveis entram no texto (itens e quantidades do orçamento, estoque atual, datas de compras registradas);
  NUNCA preço, desconto, prazo ou compatibilidade; o texto não é gerado por modelo de linguagem;
- cada acompanhamento tem cliente, instância, motivo + registro de origem, horário previsto, estado, limite de tentativas,
  motivo de cancelamento, chave de deduplicação única e histórico;
- tudo é conferido de novo NA HORA do envio (opt-out/recusa, atendimento humano, cliente voltou a falar, pausa, reclamação aberta,
  orçamento confirmado/pedido feito, estoque, janela de horário, intervalo mínimo entre contatos);
- o envio usa a fila existente (`whatsapp.send_text`, com reserva de envio por job); resultado incerto nunca é reenviado.
"""
from __future__ import annotations

import re
import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.contact import Contact
from models.job import Job, JobStatus
from models.message import Message, MessageDirection
from models.store import StoreCustomer, StoreQuote
from models.store_aftercare import StoreSupportCase
from models.store_followup import StoreFollowup
from providers.whatsapp.base import normalize_phone
from repositories.product import ProductRepository
from services import conversation_control, store_hours, store_optout
from utils.config import Settings, get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

KIND_QUOTE = "quote_resume"
KIND_RESTOCK = "restock"
STOP_HINT = "Para não receber mais contatos automáticos, responda PARAR."


class FollowupsDisabled(RuntimeError):
    """Aplicar acompanhamentos exige STORE_FOLLOWUPS_ENABLED=true (desligado por padrão)."""


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _note(fu: StoreFollowup, event: str, detail: object = None) -> None:
    fu.history = [*(fu.history or []), {"at": datetime.now(timezone.utc).isoformat(), "event": event, **({"detail": str(detail)} if detail else {})}]


# ---------------------------------------------------------------------------------------------------------------------
# Janela de horário (fuso da loja)
# ---------------------------------------------------------------------------------------------------------------------
def _margin(s: Settings) -> timedelta:
    return timedelta(minutes=s.store_followup_close_margin_minutes)


def in_window(moment: datetime, s: Settings) -> bool:
    """Contato proativo só com a loja aberta (store_hours) e fora dos últimos minutos antes de fechar."""
    return store_hours.is_open(moment, s, close_margin=_margin(s))


def next_window(moment: datetime, s: Settings) -> datetime:
    return store_hours.next_open(moment, s, close_margin=_margin(s))


# ---------------------------------------------------------------------------------------------------------------------
# Identificação e bloqueios (usados no planejamento E na hora do envio)
# ---------------------------------------------------------------------------------------------------------------------
async def contact_for_customer(db: AsyncSession, customer: StoreCustomer) -> Contact | None:
    phone = normalize_phone(customer.phone or "")
    if not phone.isdigit() or not 10 <= len(phone) <= 15:
        return None
    return await db.scalar(select(Contact).where(Contact.phone == phone))


def first_name(customer: StoreCustomer) -> str | None:
    token = (customer.name or "").strip().split(" ")[0]
    return token.capitalize() if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,20}", token) else None


async def blockers(
    db: AsyncSession, *, fu_id: int | None, contact: Contact, customer: StoreCustomer, since: datetime, now: datetime, s: Settings,
    quiet_after_since: timedelta, kind: str,
) -> str | None:
    """Motivo para NÃO contactar agora, ou None. `since` = quando o assunto começou (orçamento criado / última compra)."""
    reason = store_optout.is_blocked(contact, now)
    if reason:
        return reason
    if normalize_phone(customer.phone or "") != contact.phone:
        return "identificação do cliente não confere (telefone do cadastro × contato)"
    has_history = await db.scalar(
        select(Message.id).where(Message.contact_id == contact.id, Message.direction == MessageDirection.INBOUND,
                                 Message.whatsapp_instance == s.evolution_instance).limit(1)
    )
    if has_history is None:
        return "contato sem conversa na instância da loja"
    since = _aware(since)
    if kind == KIND_RESTOCK:
        # Reposição: o "assunto" (última compra) é antigo; o que importa é a conversa de agora e o atendimento humano recente.
        since = max(since, now - timedelta(days=7))
        active = await db.scalar(
            select(Message.id).where(Message.contact_id == contact.id, Message.whatsapp_instance == s.evolution_instance,
                                     Message.created_at >= now - quiet_after_since).limit(1)
        )
        if active is not None:
            return "conversa ativa recentemente com este cliente"
    human = await db.scalar(
        select(Message.id).where(Message.contact_id == contact.id, Message.whatsapp_instance == s.evolution_instance,
                                 Message.direction == MessageDirection.OUTBOUND, Message.sent_by_human.is_(True),
                                 Message.created_at >= since).limit(1)
    )
    if human is not None:
        return "atendimento humano na conversa"
    if kind == KIND_QUOTE:
        talked = await db.scalar(
            select(Message.id).where(Message.contact_id == contact.id, Message.whatsapp_instance == s.evolution_instance,
                                     Message.direction == MessageDirection.INBOUND, Message.created_at >= since + quiet_after_since).limit(1)
        )
        if talked is not None:
            return "cliente voltou a falar depois do assunto; a conversa seguiu"
    if (await conversation_control.snapshot(db, contact.id, s.evolution_instance))["paused"]:
        return "conversa pausada"
    open_case = await db.scalar(select(StoreSupportCase.id).where(StoreSupportCase.contact_id == contact.id, StoreSupportCase.status == "open").limit(1))
    if open_case is not None:
        return "reclamação aberta; prioridade é a equipe"
    gap_start = now - timedelta(hours=s.store_followup_min_gap_hours)
    recent = await db.scalar(
        select(StoreFollowup.id).where(
            StoreFollowup.contact_id == contact.id, StoreFollowup.status.in_(("queued", "sent", "needs_review")),
            StoreFollowup.updated_at >= gap_start, StoreFollowup.id != (fu_id or -1),
        ).limit(1)
    )
    if recent is not None:
        return "outro contato proativo recente com este cliente"
    return None


# ---------------------------------------------------------------------------------------------------------------------
# Textos (somente fatos verificáveis)
# ---------------------------------------------------------------------------------------------------------------------
def _greeting(name: str | None) -> str:
    return f"Olá{', ' + name if name else ''}! Aqui é o assistente virtual da MARQUESCOLOR."


def render_quote_resume(name: str | None, quote_id: str, available: list[dict]) -> str:
    items = [f"{it['quantity']} × {it['name']}" for it in available[:5]]
    more = len(available) - len(items)
    listing = "; ".join(items) + (f" e mais {more}" if more > 0 else "")
    return (
        f"{_greeting(name)} Seu orçamento {quote_id} venceu sem confirmação. "
        f"Itens que ainda temos em estoque: {listing}. "
        "Se ainda precisar, responda por aqui que eu refaço com preço e estoque atualizados. "
        f"{STOP_HINT}"
    )


def render_restock(name: str | None, product_name: str, days_since: int, avg_days: int) -> str:
    return (
        f"{_greeting(name)} Pelo seu histórico, a última compra de {product_name} foi há {days_since} dias "
        f"e você costuma repor a cada cerca de {avg_days} dias. Quer que eu prepare um orçamento? "
        "Respondo com preço e estoque atualizados. "
        f"{STOP_HINT}"
    )


# ---------------------------------------------------------------------------------------------------------------------
# Reposição: ciclo inferido SOMENTE de compras registradas
# ---------------------------------------------------------------------------------------------------------------------
def _parse_dt(value) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    return _aware(dt)


def restock_candidates(customer: StoreCustomer, now: datetime, s: Settings) -> list[dict]:
    by_sku: dict[str, dict[str, tuple[datetime, int]]] = {}
    for order in customer.orders or []:
        if not isinstance(order, dict) or order.get("status") == "cancelled":
            continue
        when = _parse_dt(order.get("created_at"))
        if when is None:
            continue
        for line in order.get("items") or []:
            sku, qty = line.get("sku"), line.get("quantity")
            if isinstance(sku, str) and sku and type(qty) is int and qty > 0:
                slot = by_sku.setdefault(sku, {})
                prev = slot.get(str(order.get("id")))
                slot[str(order.get("id"))] = (when, qty + (prev[1] if prev else 0))
    out = []
    for sku, orders in by_sku.items():
        rows = sorted(orders.values(), key=lambda r: r[0])
        if len(rows) < s.store_followup_restock_min_orders:
            continue
        gaps = [(b[0] - a[0]).total_seconds() / 86400 for a, b in zip(rows, rows[1:])]
        if min(gaps) < 1 or max(gaps) > 2 * min(gaps):  # compras no mesmo dia ou ritmo irregular: sem ciclo confiável
            continue
        avg = statistics.mean(gaps)
        if avg < 7:  # recompra semanal ou mais frequente: não é reposição
            continue
        last, last_qty = rows[-1]
        since_last = (now - last).total_seconds() / 86400
        if avg * (1 - s.store_followup_restock_tolerance) <= since_last <= avg * 3:
            out.append({"sku": sku, "last_purchase": last.isoformat(), "last_quantity": last_qty, "avg_days": round(avg),
                        "days_since": int(since_last), "orders": len(rows)})
    return sorted(out, key=lambda c: c["sku"])


# ---------------------------------------------------------------------------------------------------------------------
# Planejamento
# ---------------------------------------------------------------------------------------------------------------------
async def _insert(db: AsyncSession, fu: StoreFollowup) -> bool:
    try:
        async with db.begin_nested():
            db.add(fu)
            await db.flush()
        return True
    except IntegrityError:
        return False  # chave de deduplicação já existe


async def plan_quote_resumes(db: AsyncSession, *, now: datetime | None = None, apply: bool = False) -> list[dict]:
    s, now = get_settings(), now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=s.store_followup_max_age_days)
    quotes = (await db.scalars(
        select(StoreQuote).where(StoreQuote.confirmed_at.is_(None), StoreQuote.created_at >= cutoff)
        .order_by(StoreQuote.created_at).limit(s.store_followup_scan_limit)
    )).all()
    report = []
    for quote in quotes:
        due = _aware(quote.expires_at) + timedelta(minutes=s.store_followup_quote_resume_delay_minutes)
        if due > now:
            continue
        customer = await db.get(StoreCustomer, quote.customer_id)
        contact = await db.get(Contact, quote.contact_id)
        entry = {"kind": KIND_QUOTE, "origin": quote.id, "contact_id": quote.contact_id, "action": "skip", "reason": None}
        if customer is None or contact is None:
            entry["reason"] = "cadastro ou contato inexistente"
        elif any(str(o.get("id")) == quote.id for o in (customer.orders or []) if isinstance(o, dict)):
            entry["reason"] = "orçamento virou pedido"
        else:
            entry["reason"] = await blockers(db, fu_id=None, contact=contact, customer=customer, since=_aware(quote.created_at), now=now, s=s,
                                             quiet_after_since=timedelta(minutes=2), kind=KIND_QUOTE)
        if entry["reason"] is None and customer is not None and contact is not None:
            entry["action"] = "plan"
            entry["due_at"] = next_window(max(due, now), s).isoformat()
            if apply:
                fu = StoreFollowup(
                    dedupe_key=f"{KIND_QUOTE}:{quote.id}", kind=KIND_QUOTE, contact_id=contact.id, customer_id=customer.id,
                    instance=s.evolution_instance, origin_type="store_quote", origin_id=quote.id,
                    reason="orçamento vencido sem confirmação", due_at=next_window(max(due, now), s), status="scheduled",
                    max_attempts=s.store_followup_max_attempts,
                    snapshot={"quote_id": quote.id, "quote_created_at": _aware(quote.created_at).isoformat(), "items": quote.items},
                    history=[],
                )
                _note(fu, "scheduled", entry["due_at"])
                entry["action"] = "created" if await _insert(db, fu) else "exists"
        report.append(entry)
    if apply:
        await db.commit()
    return report


async def plan_restocks(db: AsyncSession, *, now: datetime | None = None, apply: bool = False, after_customer_id: int = 0) -> list[dict]:
    s, now = get_settings(), now or datetime.now(timezone.utc)
    customers = (await db.scalars(
        select(StoreCustomer).where(StoreCustomer.id > after_customer_id, StoreCustomer.phone.is_not(None))
        .order_by(StoreCustomer.id).limit(s.store_followup_scan_limit)
    )).all()
    products = ProductRepository(db)
    report = []
    for customer in customers:
        for cand in restock_candidates(customer, now, s):
            entry = {"kind": KIND_RESTOCK, "origin": f"{customer.id}:{cand['sku']}", "customer_id": customer.id, "action": "skip", "reason": None}
            product = await products.get_by_sku(cand["sku"])
            contact = await contact_for_customer(db, customer)
            if contact is None:
                entry["reason"] = "cliente sem contato com telefone válido"
            elif product is None or not product.active or product.stock_quantity < cand["last_quantity"]:
                entry["reason"] = "produto inativo ou sem estoque para a quantidade habitual"
            else:
                entry["reason"] = await blockers(db, fu_id=None, contact=contact, customer=customer, since=_parse_dt(cand["last_purchase"]) or now,
                                                 now=now, s=s, quiet_after_since=timedelta(hours=48), kind=KIND_RESTOCK)
            if entry["reason"] is None and contact is not None:
                due = next_window(now, s)
                entry.update(action="plan", due_at=due.isoformat(), candidate=cand)
                if apply:
                    fu = StoreFollowup(
                        dedupe_key=f"{KIND_RESTOCK}:{customer.id}:{cand['sku']}:{cand['last_purchase'][:10]}", kind=KIND_RESTOCK,
                        contact_id=contact.id, customer_id=customer.id, instance=s.evolution_instance, origin_type="store_customer_orders",
                        origin_id=f"{customer.id}:{cand['sku']}", reason=f"ciclo de reposição inferido de {cand['orders']} compras registradas",
                        due_at=due, status="scheduled", max_attempts=s.store_followup_max_attempts, snapshot=cand, history=[],
                    )
                    _note(fu, "scheduled", entry["due_at"])
                    entry["action"] = "created" if await _insert(db, fu) else "exists"
            report.append(entry)
    if apply:
        await db.commit()
    return report


# ---------------------------------------------------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------------------------------------------------
async def _cancel(db: AsyncSession, fu: StoreFollowup, reason: str) -> None:
    fu.status, fu.cancel_reason = "cancelled", reason
    _note(fu, "cancelled", reason)
    await db.commit()


async def _prepare_text(db: AsyncSession, fu: StoreFollowup, customer: StoreCustomer) -> tuple[str | None, str | None]:
    """(texto, motivo de cancelamento). Reconfere os fatos AGORA."""
    products = ProductRepository(db)
    name = first_name(customer)
    if fu.kind == KIND_QUOTE:
        quote = await db.get(StoreQuote, fu.origin_id, populate_existing=True)
        if quote is None:
            return None, "orçamento inexistente"
        if quote.confirmed_at is not None or quote.order_result:
            return None, "orçamento foi confirmado"
        if any(str(o.get("id")) == quote.id for o in (customer.orders or []) if isinstance(o, dict)):
            return None, "orçamento virou pedido"
        available = []
        for line in quote.items or []:
            product = await products.get_by_sku(str(line.get("sku")))
            qty = line.get("quantity")
            if product is not None and product.active and type(qty) is int and qty > 0 and product.stock_quantity >= qty:
                available.append({"name": product.name, "quantity": qty})
        if not available:
            return None, "nenhum item do orçamento está disponível agora"
        return render_quote_resume(name, quote.id, available), None
    if fu.kind == KIND_RESTOCK:
        cand = fu.snapshot or {}
        product = await products.get_by_sku(str(cand.get("sku")))
        if product is None or not product.active or product.stock_quantity < int(cand.get("last_quantity") or 1):
            return None, "produto inativo ou sem estoque"
        last = _parse_dt(cand.get("last_purchase"))
        if last is None:
            return None, "data da última compra ilegível"
        orders_after = [o for o in (customer.orders or []) if isinstance(o, dict) and (_parse_dt(o.get("created_at")) or last) > last
                        and any(it.get("sku") == cand.get("sku") for it in (o.get("items") or []))]
        if orders_after:
            return None, "cliente já recomprou o item"
        return render_restock(name, product.name, int(cand.get("days_since", 0)), int(cand.get("avg_days", 0))), None
    return None, f"tipo de acompanhamento desconhecido: {fu.kind}"


async def run_due(db: AsyncSession, *, now: datetime | None = None, apply: bool = False, limit: int | None = None) -> list[dict]:
    s, now = get_settings(), now or datetime.now(timezone.utc)
    if apply and not s.store_followups_enabled:
        raise FollowupsDisabled("STORE_FOLLOWUPS_ENABLED=false: acompanhamentos desligados (use a simulação)")
    due = (await db.scalars(
        select(StoreFollowup).where(StoreFollowup.status == "scheduled", StoreFollowup.due_at <= now)
        .order_by(StoreFollowup.due_at, StoreFollowup.id).limit(limit or s.store_followup_scan_limit)
    )).all()
    report = []
    for fu in due:
        entry: dict = {"followup_id": fu.id, "kind": fu.kind, "action": None, "reason": None}
        reason: str | None
        report.append(entry)
        customer = await db.get(StoreCustomer, fu.customer_id, populate_existing=True)
        contact = await db.get(Contact, fu.contact_id, populate_existing=True)
        if fu.attempts >= fu.max_attempts:
            if apply:
                fu.status = "exhausted"
                _note(fu, "exhausted")
                await db.commit()
            entry.update(action="exhausted")
            continue
        if customer is None or contact is None:
            reason = "cadastro ou contato inexistente"
        elif fu.instance != s.evolution_instance or (s.evolution_personal_instance and fu.instance == s.evolution_personal_instance):
            reason = "instância não é a da loja"
        else:
            since = _aware(fu.created_at)
            if fu.kind == KIND_QUOTE:
                quote = await db.get(StoreQuote, fu.origin_id)
                since = _aware(quote.created_at) if quote is not None else since
                quiet = timedelta(minutes=2)
            else:
                since = _parse_dt((fu.snapshot or {}).get("last_purchase")) or since
                quiet = timedelta(hours=48)
            reason = await blockers(db, fu_id=fu.id, contact=contact, customer=customer, since=since, now=now, s=s, quiet_after_since=quiet, kind=fu.kind)
        content: str | None = None
        if reason is None and customer is not None and contact is not None:
            content, reason = await _prepare_text(db, fu, customer)
        if reason is not None:
            entry.update(action="cancel", reason=reason)
            if apply:
                await _cancel(db, fu, reason)
            continue
        if not in_window(now, s):
            entry.update(action="defer", reason="fora da janela de horário")
            if apply:
                fu.due_at = next_window(now, s)
                _note(fu, "deferred", fu.due_at.isoformat())
                await db.commit()
            continue
        if not apply:
            entry.update(action="dry_run", text=content)
            continue
        if contact is None or content is None:  # impossível aqui (reason seria não nulo); satisfaz o verificador de tipos
            continue
        fu.status, fu.attempts = "queued", fu.attempts + 1
        payload: dict = {"to": contact.phone, "content": content, "instance": fu.instance, "followup_id": fu.id}
        if s.store_voice_enabled:
            payload["voice_companion"] = {"followup_id": fu.id}   # só vira áudio se o cliente PEDIU áudio (store_voice.decide)
        job = Job(name="whatsapp.send_text", payload=payload, max_attempts=s.jobs_default_max_attempts, scheduled_at=now)
        db.add(job)
        await db.flush()
        fu.job_id = job.id
        _note(fu, "queued", f"job {job.id}")
        await db.commit()
        entry.update(action="queued", job_id=job.id, text=content)
    return report


async def reconcile(db: AsyncSession, *, stale_minutes: int = 15) -> dict[str, int]:
    """Fecha o ciclo dos acompanhamentos 'queued' olhando o job e a reserva de envio. Nunca reenvia."""
    counts = {"sent": 0, "needs_review": 0, "cancelled": 0}
    now = datetime.now(timezone.utc)
    rows = (await db.scalars(select(StoreFollowup).where(StoreFollowup.status == "queued"))).all()
    for fu in rows:
        if fu.job_id is None:
            if (now - _aware(fu.updated_at)).total_seconds() > stale_minutes * 60:
                fu.status = "needs_review"
                _note(fu, "needs_review", "job de envio não foi criado")
                counts["needs_review"] += 1
            continue
        job = await db.get(Job, fu.job_id, populate_existing=True)
        if job is None or job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            continue
        intent = (await db.execute(text("SELECT status FROM conversation_send_intents WHERE id=:i"), {"i": f"send-job:{fu.job_id}"})).scalar()
        if job.status == JobStatus.SUCCEEDED and intent == "sent":
            fu.status, fu.sent_at = "sent", _aware(job.finished_at or now)
            _note(fu, "sent", f"job {fu.job_id}")
            counts["sent"] += 1
        elif job.status == JobStatus.SUCCEEDED and intent is None:
            fu.status, fu.cancel_reason = "cancelled", "envio suprimido antes do transporte (pausa ou reserva existente)"
            _note(fu, "cancelled", fu.cancel_reason)
            counts["cancelled"] += 1
        else:
            fu.status = "needs_review"
            _note(fu, "needs_review", f"job {job.status.value}; reserva={intent}; não reenviado automaticamente")
            counts["needs_review"] += 1
    await db.commit()
    return counts
