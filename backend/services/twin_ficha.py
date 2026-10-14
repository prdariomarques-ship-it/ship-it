"""Ficha do dono para o Twin: fatos autorizados, quem e cada contato e quem e prioridade.

Por que existe: o Twin inventou um e-mail (10:01 de 14/10, mensagem 11267) e cumprimentou "Jonathan" um contato que o dono salvou como
"nathan2" -- `Contact.name` vem do nome de perfil do WhatsApp, nao da agenda do dono. A ficha da ao Twin o que ele PODE afirmar e diz quem esta
do outro lado.

Niveis (o que cada contato recebe):
  - todos:   `public` (ex.: nome, ministerio, loja, e-mail "so se pedirem");
  - familia: tambem `family_only` (ex.: cidade, parentes) e a relacao de quem esta falando;
  - dados que nao devem ir ao agente (nome completo da mae, idade, empregador) simplesmente NAO entram no arquivo.
Contatos `priority` (chefes, cliente importante): o Twin NAO responde sozinho; o dono e avisado na hora (decisao do dono, 14/10).

O arquivo JSON mora so no servidor (dados pessoais), nunca no Git. Recarrega sozinho quando o arquivo muda. Qualquer erro de leitura
devolve "sem ficha" -- o Twin segue como antes, nunca quebra.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

GROUP_FAMILY = "family"
GROUP_PRIORITY = "priority"

_FACTS_HEADER = (
    "Fatos autorizados sobre o Dário. Afirme SOMENTE o que está aqui ou na conversa; o que não estiver, não invente: "
    "diga que confirma depois. Nunca escreva e-mail, telefone, PIX, CPF/CNPJ ou link que não esteja aqui ou na conversa."
)


@dataclass(frozen=True)
class FichaEntry:
    name: str
    relation: str
    group: str
    contact_ids: frozenset[int]
    phone_suffixes: tuple[str, ...]


@dataclass(frozen=True)
class Ficha:
    public: tuple[str, ...]
    family_only: tuple[str, ...]
    entries: tuple[FichaEntry, ...]

    def entry_for(self, contact_id: int | None, phone: str | None) -> FichaEntry | None:
        digits = re.sub(r"\D", "", phone or "")
        for entry in self.entries:
            if contact_id is not None and contact_id in entry.contact_ids:
                return entry
            if digits and any(digits.endswith(suffix) for suffix in entry.phone_suffixes):
                return entry
        return None


def _strings(value: object) -> tuple[str, ...]:
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip()) if isinstance(value, list) else ()


def parse_ficha(raw: object) -> Ficha:
    if not isinstance(raw, dict):
        raise ValueError("ficha: raiz deve ser um objeto")
    entries = []
    for item in raw.get("contacts") or []:
        match = item.get("match") or {}
        ids = frozenset(int(i) for i in match.get("contact_ids") or [])
        suffixes = tuple(re.sub(r"\D", "", str(s)) for s in match.get("phone_suffixes") or [])
        suffixes = tuple(s for s in suffixes if len(s) >= 8)  # sufixo curto demais casaria com gente errada
        if not ids and not suffixes:
            raise ValueError("ficha: contato sem contact_ids nem phone_suffixes validos")
        entries.append(
            FichaEntry(
                name=str(item.get("name") or "").strip(),
                relation=str(item.get("relation") or "").strip(),
                group=str(item.get("group") or "").strip(),
                contact_ids=ids,
                phone_suffixes=suffixes,
            )
        )
    return Ficha(public=_strings(raw.get("public")), family_only=_strings(raw.get("family_only")), entries=tuple(entries))


_cache: dict[str, tuple[float, Ficha]] = {}


def get_ficha() -> Ficha | None:
    """A ficha configurada ou None (desligada, ausente ou invalida: nunca levanta)."""
    path = get_settings().twin_ficha_path
    if not path:
        return None
    try:
        mtime = Path(path).stat().st_mtime
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        ficha = parse_ficha(json.loads(Path(path).read_text(encoding="utf-8")))
        _cache[path] = (mtime, ficha)
        return ficha
    except Exception:  # noqa: BLE001 - a ficha e opcional; o Twin segue sem ela
        logger.warning("Ficha do Twin indisponivel; o Twin segue sem ela", exc_info=True)
        return None


def lookup(contact_id: int | None, phone: str | None) -> tuple[Ficha | None, FichaEntry | None]:
    ficha = get_ficha()
    return ficha, (ficha.entry_for(contact_id, phone) if ficha else None)


def is_priority(entry: FichaEntry | None) -> bool:
    return entry is not None and entry.group == GROUP_PRIORITY


def display_name(contact_name: str, entry: FichaEntry | None) -> str:
    """O nome do dono para o contato (agenda), nao o do perfil do WhatsApp."""
    return entry.name if entry and entry.name else contact_name


def build_ficha_blocks(ficha: Ficha | None, entry: FichaEntry | None) -> list[str]:
    if ficha is None:
        return []
    facts = list(ficha.public)
    if entry is not None and entry.group == GROUP_FAMILY:
        facts += ficha.family_only
    blocks = [_FACTS_HEADER + "\n" + "\n".join(f"- {fact}" for fact in facts)] if facts else []
    if entry is not None and entry.name:
        who = f"Quem está falando agora: {entry.name}" + (f", {entry.relation} do Dário." if entry.relation else ".")
        blocks.append(who)
    return blocks
