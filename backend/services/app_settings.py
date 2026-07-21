"""A small, explicit registry of runtime settings the admin dashboard can
show and, for a chosen few, actually edit — everything else in
`utils.config.Settings` stays purely `.env`-sourced, unreachable from here.

`Settings()` (`utils/config.py`) remains the single source of truth at
every read site in the app (`settings.auto_reply_enabled`, etc.) — this
module only ever *layers a persisted override on top of it* (mutates the
live, `@lru_cache`d singleton in place) and *records* that override in the
`app_settings` table so it survives a restart. No parallel config system,
no new provider/factory pattern.

Adding a new editable setting later is one new `SettingDef` entry in
`SETTINGS_CATALOG` below (plus, if the value type isn't already handled,
one branch in `_coerce`/`_serialize`) — no change to the endpoints, the
repository, or the startup hook.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.app_setting import AppSettingRepository
from utils.config import Settings, get_settings

ValueType = Literal["bool", "str"]


@dataclass(frozen=True)
class SettingDef:
    key: str
    attr: str  # attribute name on Settings
    description: str
    category: str
    editable: bool
    value_type: ValueType


# The only settings the dashboard exposes today (the "Comportamento" card).
# Provider selection (llm/whatsapp/mail/calendar/contacts/drive) stays out
# of this catalog entirely -- each already has its own `@lru_cache`d factory
# holding live client state, so editing one at runtime would leave stale
# connections behind; that's a materially bigger feature (cache
# invalidation, in-flight request handling), not a plain settings edit. See
# ROADMAP for both this and `jobs_enabled` (gates whether the job worker
# task is even started at boot -- editing it live needs worker start/stop
# lifecycle, not just a flag flip).
SETTINGS_CATALOG: list[SettingDef] = [
    SettingDef(
        key="auto_reply_enabled",
        attr="auto_reply_enabled",
        description=(
            "Resposta automática do assistente a mensagens recebidas no WhatsApp."
        ),
        category="behavior",
        editable=True,
        value_type="bool",
    ),
    SettingDef(
        key="jobs_enabled",
        attr="jobs_enabled",
        description=(
            "Fila de jobs em segundo plano (worker). Só é lida na inicialização do "
            "processo -- editar aqui não liga/desliga o worker; exige reiniciar via "
            "variável de ambiente (JOBS_ENABLED)."
        ),
        category="behavior",
        editable=False,
        value_type="bool",
    ),
    SettingDef(
        key="environment",
        attr="environment",
        description="Ambiente de execução do backend (development/production/test).",
        category="behavior",
        editable=False,
        value_type="str",
    ),
]

_BY_KEY: dict[str, SettingDef] = {item.key: item for item in SETTINGS_CATALOG}


class UnknownSettingError(ValueError):
    pass


class SettingNotEditableError(ValueError):
    pass


def _serialize(value_type: ValueType, value: object) -> str:
    if value_type == "bool":
        return "true" if bool(value) else "false"
    return str(value)


def _coerce(value_type: ValueType, raw: str) -> bool | str:
    if value_type == "bool":
        return raw.strip().lower() == "true"
    return raw


async def apply_persisted_overrides(db: AsyncSession) -> None:
    """Called once at startup (`main.py`'s `lifespan`), after `Settings()`
    is first constructed and before anything reads a value this module
    covers. Layers any admin-set override from `app_settings` on top of the
    `.env` default -- so a dashboard edit survives a restart instead of
    silently reverting."""
    settings = get_settings()
    repo = AppSettingRepository(db)
    for definition in SETTINGS_CATALOG:
        if not definition.editable:
            continue
        row = await repo.get_by_key(definition.key)
        if row is None:
            continue
        setattr(settings, definition.attr, _coerce(definition.value_type, row.value))


async def list_settings(db: AsyncSession) -> list[dict]:
    settings = get_settings()
    repo = AppSettingRepository(db)
    rows = {row.key: row for row in await repo.list_all()}
    result = []
    for definition in SETTINGS_CATALOG:
        row = rows.get(definition.key)
        result.append(
            {
                "key": definition.key,
                "value": getattr(settings, definition.attr),
                "description": definition.description,
                "category": definition.category,
                "editable": definition.editable,
                "updated_at": row.updated_at if row else None,
                "updated_by": row.updated_by if row else None,
            }
        )
    return result


async def update_setting(
    db: AsyncSession, key: str, value: bool | int | str, updated_by: int | None
) -> dict:
    definition = _BY_KEY.get(key)
    if definition is None:
        raise UnknownSettingError(f"Configuração desconhecida: {key!r}")
    if not definition.editable:
        raise SettingNotEditableError(
            f"Configuração {key!r} é somente leitura (editar exige reiniciar o processo)."
        )

    serialized = _serialize(definition.value_type, value)
    row = await AppSettingRepository(db).upsert(
        key=definition.key,
        value=serialized,
        description=definition.description,
        category=definition.category,
        editable=True,
        updated_by=updated_by,
    )

    settings: Settings = get_settings()
    setattr(settings, definition.attr, _coerce(definition.value_type, serialized))

    return {
        "key": definition.key,
        "value": getattr(settings, definition.attr),
        "description": definition.description,
        "category": definition.category,
        "editable": True,
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }
