"""Recusa e pedido para não receber contatos, na conversa da LOJA.

Só mensagens CURTAS e inequívocas são classificadas (frase inteira, não trecho): "PARAR", "não quero receber mais mensagens",
"só texto", "não tenho interesse". Uma frase longa nunca é tratada como opt-out por casar uma palavra solta.

- opt-out    -> `store_contact_opt_out` + `store_followup_opt_out` (esta é a chave que o pós-venda de produção já respeita);
                cancela acompanhamentos e áudios pendentes;
- recusa     -> pausa os acompanhamentos por `store_followup_refusal_cooldown_days` (não é opt-out permanente);
- só texto   -> `reply_mode = "texto"` e `voice_opt_out` (o cliente continua sendo atendido normalmente).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models.contact import Contact
from models.message import Message
from models.store_followup import StoreFollowup
from models.store_voice import StoreVoiceSend
from utils.config import get_settings

OPTOUT, REFUSAL, TEXT_ONLY = "optout", "refusal", "text_only"

ACK_OPTOUT = "Pronto: não vou mais enviar contatos automáticos. Se precisar de algo, é só chamar por aqui."
ACK_REFUSAL = "Tudo bem, obrigado por avisar. Se precisar de algo, é só chamar por aqui."
ACK_TEXT_ONLY = "Combinado: daqui para frente respondo só por texto."

_MAX_LEN = 80
_OPTOUT = re.compile(
    r"^(por favor )?("
    r"parar( de (me )?(enviar|mandar)( (mensagens?|contatos?|nada))?)?|pare( de (me )?(enviar|mandar)( (mensagens?|contatos?|nada))?)?|parem|"
    r"sair|stop|cancelar|descadastrar|remover|"
    r"nao (me )?(envie|enviem|mande|mandem|procure|procurem) mais( (mensagens?|contatos?|nada))?|"
    r"nao quero (mais )?receber( mais)?( (mensagens?|contatos?|nada|promocoes?|ofertas?))?|"
    r"nao quero (mais )?(mensagens?|contatos?|promocoes?|ofertas?)|"
    r"me (tire|tirem|retire|retirem|remova|removam) da lista|tire meu numero|"
    r"nao entre mais em contato|nao me chame mais"
    r")( (obrigado|obrigada|obg|valeu|por favor))?$"
)
_REFUSAL = re.compile(
    r"^(nao tenho interesse|sem interesse|nao tenho mais interesse|nao quero|nao quero nao|nao quero obrigado|nao quero obrigada|"
    r"nao preciso|nao preciso mais|nao obrigado|nao obrigada|ja comprei|ja resolvi|desisti|deixa pra la|nao vou comprar|nao vou querer)"
    r"( (obrigado|obrigada|obg|valeu|por favor))?$"
)
_TEXT_ONLY = re.compile(
    r"^(so texto|somente texto|apenas texto|so por texto|so escrito|(por favor )?(nao )?(me )?(mande|envie|manda|envia|quero) (mais )?audios?( nao)?|"
    r"nao quero (mais )?audios?|prefiro texto|prefiro escrito|prefiro mensagem escrita|pode ser so texto|texto por favor|sem audios?)"
    r"( (obrigado|obrigada|obg|valeu|por favor))?$"
)


def normalize(text: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    folded = re.sub(r"[^a-z0-9 ]+", " ", folded)
    return " ".join(folded.split())


def classify(text: str) -> str | None:
    norm = normalize(text)
    if not norm or len(norm) > _MAX_LEN:
        return None
    # "não quero áudios" é preferência de formato, não recusa nem opt-out: confere antes dos demais.
    if _TEXT_ONLY.match(norm):
        return TEXT_ONLY
    if _OPTOUT.match(norm):
        return OPTOUT
    if _REFUSAL.match(norm):
        return REFUSAL
    return None


async def _cancel_pending(db: AsyncSession, contact_id: int, reason: str, *, voice_too: bool = True) -> int:
    now = datetime.now(timezone.utc)
    followups = await db.execute(
        update(StoreFollowup).where(StoreFollowup.contact_id == contact_id, StoreFollowup.status == "scheduled")
        .values(status="cancelled", cancel_reason=reason, updated_at=now)
    )
    count = getattr(followups, "rowcount", 0) or 0
    if voice_too:
        await db.execute(
            update(StoreVoiceSend).where(StoreVoiceSend.contact_id == contact_id, StoreVoiceSend.status == "queued")
            .values(status="cancelled", reason=reason, updated_at=now)
        )
    return count


async def handle_inbound(db: AsyncSession, contact: Contact, message: Message) -> str | None:
    """Se a mensagem do cliente for opt-out/recusa/só texto, aplica o efeito, confirma ao cliente e devolve o texto de
    confirmação (o chamador envia e NÃO chama o agente). Caso contrário devolve None sem tocar em nada."""
    kind = classify(message.content or "")
    if kind is None:
        return None
    s = get_settings()
    now = datetime.now(timezone.utc)
    prefs = dict(contact.preferences or {})
    if kind == OPTOUT:
        prefs.update(store_contact_opt_out=True, store_followup_opt_out=True, store_contact_opt_out_at=now.isoformat(),
                     store_contact_opt_out_message_id=message.id)
        reply = ACK_OPTOUT
    elif kind == REFUSAL:
        prefs["store_followup_paused_until"] = (now + timedelta(days=s.store_followup_refusal_cooldown_days)).isoformat()
        reply = ACK_REFUSAL
    else:
        prefs.update(reply_mode="texto", voice_opt_out=True)
        reply = ACK_TEXT_ONLY
    contact.preferences = prefs
    if kind == TEXT_ONLY:
        await db.execute(update(StoreVoiceSend).where(StoreVoiceSend.contact_id == contact.id, StoreVoiceSend.status == "queued")
                         .values(status="cancelled", reason="cliente pediu só texto", updated_at=now))
    else:
        await _cancel_pending(db, contact.id, "cliente recusou" if kind == REFUSAL else "cliente pediu para não receber contatos")
    await db.commit()
    return reply


def is_blocked(contact: Contact, now: datetime | None = None) -> str | None:
    """Motivo pelo qual NENHUM contato proativo deve ser feito a este contato agora, ou None."""
    prefs = contact.preferences or {}
    if prefs.get("store_contact_opt_out") or str(prefs.get("store_followup_opt_out", "")).lower() == "true" or prefs.get("store_followup_opt_out") is True:
        return "cliente pediu para não receber contatos"
    until = prefs.get("store_followup_paused_until")
    if until:
        try:
            if datetime.fromisoformat(str(until)) > (now or datetime.now(timezone.utc)):
                return "cliente recusou recentemente"
        except ValueError:
            return "pausa de acompanhamento ilegível"
    return None
