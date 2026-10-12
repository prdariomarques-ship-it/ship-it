"""Atualização de `Contact.preferences` pela API (PATCH /contacts/{id}).

Antes, o PATCH SUBSTITUÍA o dicionário inteiro pelo enviado pelo cliente HTTP: um payload vazio ou antigo apagava o PARAR já
registrado, sem precisar de concorrência. Agora o PATCH MESCLA:

- relê o contato do banco sob trava de linha (`ContactRepository.lock_fresh`) e só então calcula o resultado;
- chaves comuns: o valor enviado substitui o armazenado; `null` remove a chave; as não enviadas ficam como estão (payload vazio
  não muda nada);
- chaves protegidas (`store_optout.PROTECTED_PREFERENCE_KEYS`: opt-out, pausa por recusa e seus metadados) NÃO podem ser
  afrouxadas por esta rota: enviar o MESMO valor já armazenado (mesmo tipo: `1`/`1.0`/`"true"` não valem por `true`) é inofensivo (round-trip de um formulário) e o valor armazenado é o que permanece; a única mudança
  aceita é um operador registrar o opt-out (`store_contact_opt_out`/`store_followup_opt_out` = true), que só restringe. Qualquer
  outro valor — `false` para tirar um opt-out, valor antigo, metadado diferente — recusa a requisição inteira com 422.
  Reativar contatos de quem pediu para parar exige uma ação própria e explícita (decisão pendente), não um PATCH genérico.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.contact import Contact
from repositories.contact import ContactRepository
from services.store_optout import PROTECTED_PREFERENCE_KEYS


def _same(incoming: Any, stored: Any) -> bool:
    """Igualdade ESTRITA (tipo e valor): em Python `1 == True` e `1.0 == True`, mas `1` não é reconhecido como opt-out por
    `store_optout.is_blocked`; aceitar o número como "igual" e gravá-lo derrubaria o bloqueio efetivo."""
    return type(incoming) is type(stored) and incoming == stored


_RESTRICTIVE_FLAGS = frozenset({"store_contact_opt_out", "store_followup_opt_out"})


async def prepare_contact_update(db: AsyncSession, item: Contact, data: dict[str, Any]) -> dict[str, Any]:
    """Devolve os campos a gravar. Só mexe em `preferences`; levanta HTTP 422 se o payload tentar alterar chave protegida."""
    if "preferences" not in data:
        return data
    incoming = data["preferences"]
    if incoming is None:                      # "sem alteração" (antes gravava None e quebrava o contrato do campo)
        return {k: v for k, v in data.items() if k != "preferences"}
    fresh = await ContactRepository(db).lock_fresh(item.id)
    stored = dict((fresh.preferences if fresh is not None else item.preferences) or {})
    conflicts = sorted(
        k for k in incoming
        if k in PROTECTED_PREFERENCE_KEYS and not _same(incoming[k], stored.get(k)) and not (k in _RESTRICTIVE_FLAGS and incoming[k] is True)
    )
    if conflicts:
        await db.rollback()                   # solta a trava de linha antes de recusar
        raise HTTPException(
            status_code=422,
            detail=f"As preferências {conflicts} são protegidas (opt-out/recusa do cliente) e não podem ser alteradas por esta rota.",
        )
    merged = dict(stored)
    for key, value in incoming.items():
        if key in PROTECTED_PREFERENCE_KEYS:
            if key in _RESTRICTIVE_FLAGS and incoming[key] is True:
                merged[key] = True            # operador registrando o opt-out: só o booleano verdadeiro
            continue                          # os demais protegidos: o valor ARMAZENADO é preservado, nunca o recebido
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return {**data, "preferences": merged}
