"""Recusa e pedido para não receber contatos, na conversa da LOJA.

Só mensagens CURTAS e inequívocas são classificadas (frase inteira, não trecho): "PARAR", "não quero receber mais mensagens",
"só texto", "não tenho interesse". Uma frase longa nunca é tratada como opt-out por casar uma palavra solta.

- opt-out    -> `store_contact_opt_out` + `store_followup_opt_out` (esta é a chave que o pós-venda de produção já respeita);
                cancela acompanhamentos e áudios pendentes;
- recusa     -> pausa os acompanhamentos por `store_followup_refusal_cooldown_days` (não é opt-out permanente);
- só texto   -> `reply_mode = "texto"` e `voice_opt_out` (o cliente continua sendo atendido normalmente);
- pedir áudio-> PEDIDO AFIRMATIVO ("quero áudio", "mande áudio"): nunca é recusa. Vale como a preferência mais recente do
                cliente para a VOZ: grava `reply_mode = "audio"` e limpa `voice_opt_out` (um "só texto" anterior é revertido,
                porque o cliente mudou de ideia). Não reverte opt-out de contatos nem recusa (`store_contact_opt_out`,
                `store_followup_opt_out`, pausa por recusa): isso só o próprio cliente muda, falando com a equipe.
                O agente continua respondendo normalmente (não há interceptação nem mensagem de confirmação).

Este módulo roda no fluxo da loja ANTES do agente, independentemente das chaves STORE_VOICE_ENABLED e STORE_FOLLOWUPS_ENABLED:
com as duas desligadas, "PARAR"/"só texto" ainda são reconhecidos, gravados e confirmados ao cliente.
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
from repositories.contact import ContactRepository
from services import conversation_control
from utils.config import get_settings

ACK_OPTOUT = "Pronto: não vou mais enviar contatos automáticos. Se precisar de algo, é só chamar por aqui."
ACK_REFUSAL = "Tudo bem, obrigado por avisar. Se precisar de algo, é só chamar por aqui."
ACK_TEXT_ONLY = "Combinado: daqui para frente respondo só por texto."

# Chaves que só o fluxo de recusa do cliente escreve; nenhum outro escritor de `Contact.preferences` pode alterá-las.
PROTECTED_PREFERENCE_KEYS = frozenset({
    "store_contact_opt_out", "store_followup_opt_out", "store_contact_opt_out_at", "store_contact_opt_out_message_id",
    "store_followup_paused_until",
})

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
_POLITE = r"( (obrigado|obrigada|obg|valeu|por favor))?$"
# NEGATIVO: o cliente NÃO quer áudio / quer só texto. A negação é obrigatória em todas as formas com "áudio".
_TEXT_ONLY = re.compile(
    r"^(so texto|somente texto|apenas texto|so por texto|so escrito|prefiro texto|prefiro escrito|prefiro mensagem escrita|"
    r"pode ser so texto|texto por favor|sem audios?|"
    r"(por favor )?nao (me )?(mande|mandem|manda|envie|enviem|envia) (mais )?audios?|"
    r"(por favor )?(me )?(mande|manda|envie|envia|quero) (mais )?audios? nao|"
    r"nao quero (mais )?(receber )?audios?)" + _POLITE
)
# AFIRMATIVO: o cliente PEDE áudio. Sem nenhuma negação (a frase inteira é conferida: "quero áudio não" cai no negativo acima).
_AUDIO_REQUEST = re.compile(
    r"^(por favor )?(pode )?(me )?(mandar|enviar|mande|manda|envie|envia|quero|queria|prefiro|gostaria de receber|pode ser) "
    r"(um |o |mais )?(audios?|mensage(m|ns) de voz|voz)" + _POLITE
)
OPTOUT, REFUSAL, TEXT_ONLY, AUDIO_REQUEST = "optout", "refusal", "text_only", "audio_request"


def normalize(text: str) -> str:
    folded = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
    folded = re.sub(r"[^a-z0-9 ]+", " ", folded)
    return " ".join(folded.split())


def classify(text: str) -> str | None:
    norm = normalize(text)
    if not norm or len(norm) > _MAX_LEN:
        return None
    # "não quero áudios" é preferência de formato, não recusa nem opt-out: confere antes dos demais. O pedido AFIRMATIVO de
    # áudio vem depois do negativo e nunca é tratado como recusa.
    if _TEXT_ONLY.match(norm):
        return TEXT_ONLY
    if _AUDIO_REQUEST.match(norm):
        return AUDIO_REQUEST
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


async def locked_preferences(db: AsyncSession, contact: Contact, instance: str) -> tuple[Contact, dict]:
    """Ponto ÚNICO para quem vai gravar `preferences` de um contato: toma a trava da conversa (ordem em relação a um envio
    proativo que confere e reserva sob a mesma trava) e RELÊ o contato do banco com trava de linha. O objeto recebido pode ter
    sido carregado antes das travas; gravar o dicionário dele apagaria o que outro escritor confirmou nesse intervalo.
    Devolve (contato atualizado, cópia do dicionário relido). Não faz commit."""
    await conversation_control.lock_scope(db, contact.id, instance)
    fresh = await ContactRepository(db).lock_fresh(contact.id)
    contact = fresh if fresh is not None else contact
    return contact, dict(contact.preferences or {})


async def mark_opt_out(db: AsyncSession, contact: Contact, *, instance: str, message_id: int | None = None) -> Contact:
    """Grava o opt-out permanente de contatos (mesmas chaves que a loja e o pós-venda de produção respeitam), com a releitura
    travada. Destinado também ao `stop_followups` do pós-venda quando ele for integrado. Não faz commit."""
    contact, prefs = await locked_preferences(db, contact, instance)
    prefs.update(store_contact_opt_out=True, store_followup_opt_out=True, store_contact_opt_out_at=datetime.now(timezone.utc).isoformat(),
                 store_contact_opt_out_message_id=message_id)
    contact.preferences = prefs
    return contact


async def handle_inbound(db: AsyncSession, contact: Contact, message: Message) -> str | None:
    """Se a mensagem do cliente for opt-out/recusa/só texto, aplica o efeito, confirma ao cliente e devolve o texto de
    confirmação (o chamador envia e NÃO chama o agente). Caso contrário devolve None sem tocar em nada."""
    kind = classify(message.content or "")
    if kind is None:
        return None
    s = get_settings()
    now = datetime.now(timezone.utc)
    contact, prefs = await locked_preferences(db, contact, message.whatsapp_instance or s.evolution_instance)
    if kind == AUDIO_REQUEST:
        prefs.update(reply_mode="audio", voice_opt_out=False)
        contact.preferences = prefs
        await db.commit()
        return None  # nenhuma interceptação: o agente responde normalmente (e, havendo voz habilitada, também por áudio)
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
