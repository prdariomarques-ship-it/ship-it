"""Google Calendar connection endpoints — admin-only setup, not a chat
surface. Mirrors `mail/router.py` exactly; see there for the full rationale
of every design choice repeated here (state-token auth for the callback,
admin-only management, best-effort account label, HTML-escaped result page).
"""

from datetime import datetime, timezone
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import create_oauth_state_token, decode_oauth_state_token
from auth.permissions import require_admin
from database.session import get_db
from gcalendar.schemas import GCalendarConnectResponse, GCalendarStatusResponse
from models.user import User
from providers.calendar.base import CalendarProviderError
from providers.calendar.factory import get_calendar_provider
from repositories.gcalendar_account import GoogleCalendarAccountRepository
from repositories.user import UserRepository
from services.token_crypto import TokenEncryptionNotConfigured, encrypt_token
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/gcalendar", tags=["gcalendar"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

_STATE_PURPOSE = "gcalendar_oauth_state"


def _require_configured() -> None:
    from utils.config import get_settings

    settings = get_settings()
    if not (
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_calendar_redirect_uri
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar integration is not configured "
            "(GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_CALENDAR_REDIRECT_URI)",
        )


@router.get(
    "/connect",
    response_model=GCalendarConnectResponse,
    dependencies=[Depends(require_admin)],
)
async def connect(
    current_user: Annotated[User, Depends(require_admin)],
) -> GCalendarConnectResponse:
    _require_configured()
    provider = get_calendar_provider()
    state = create_oauth_state_token(current_user.id, purpose=_STATE_PURPOSE)
    return GCalendarConnectResponse(authorization_url=provider.authorization_url(state))


@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    db: DbSession,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    if error:
        return _result_page(ok=False, message=f"Google recusou a autorização: {error}")
    if not code or not state:
        return _result_page(ok=False, message="Requisição de callback incompleta.")

    user_id = decode_oauth_state_token(state, purpose=_STATE_PURPOSE)
    if user_id is None:
        return _result_page(
            ok=False,
            message="Sessão de autorização inválida ou expirada. Tente conectar de novo.",
        )

    user = await UserRepository(db).get(user_id)
    if user is None:
        return _result_page(ok=False, message="Usuário não encontrado.")

    provider = get_calendar_provider()
    try:
        tokens = await provider.exchange_code(code)
    except CalendarProviderError as exc:
        logger.error("Google Calendar OAuth code exchange failed: %s", exc)
        return _result_page(
            ok=False, message="Não foi possível concluir a autorização com o Google."
        )

    if not tokens.refresh_token:
        return _result_page(
            ok=False,
            message="O Google não retornou um refresh token. Revogue o acesso anterior em "
            "myaccount.google.com/permissions e tente conectar de novo.",
        )

    try:
        encrypted = encrypt_token(tokens.refresh_token)
    except TokenEncryptionNotConfigured as exc:
        logger.error("Cannot store Google Calendar refresh token: %s", exc)
        return _result_page(
            ok=False,
            message="Armazenamento de credenciais não configurado no servidor.",
        )

    account_label = await _resolve_account_label(provider, tokens.access_token)

    await GoogleCalendarAccountRepository(db).upsert_for_user(
        user.id,
        provider.name,
        account_label=account_label,
        encrypted_refresh_token=encrypted,
        scopes=tokens.scope.split(),
        connected_at=datetime.now(timezone.utc),
    )

    return _result_page(
        ok=True, message=f"Google Calendar ({account_label}) conectado com sucesso."
    )


@router.get(
    "/status",
    response_model=GCalendarStatusResponse,
    dependencies=[Depends(require_admin)],
)
async def gcalendar_status(
    db: DbSession, current_user: Annotated[User, Depends(require_admin)]
) -> GCalendarStatusResponse:
    account = await GoogleCalendarAccountRepository(db).get_by_user(
        current_user.id, get_calendar_provider().name
    )
    if account is None:
        return GCalendarStatusResponse(connected=False)
    return GCalendarStatusResponse(
        connected=True,
        account_label=account.account_label,
        connected_at=account.connected_at,
    )


@router.delete(
    "/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def disconnect(
    db: DbSession, current_user: Annotated[User, Depends(require_admin)]
) -> None:
    repository = GoogleCalendarAccountRepository(db)
    account = await repository.get_by_user(
        current_user.id, get_calendar_provider().name
    )
    if account is not None:
        await repository.delete(account)


async def _resolve_account_label(provider, access_token: str) -> str:
    """Best-effort — the primary calendar's summary, or a generic label if
    that lookup fails for any reason; connection still succeeds either way."""
    try:
        calendars = await provider.list_calendars(access_token)
        primary = next((c for c in calendars if c.primary), None)
        if primary and primary.summary:
            return primary.summary
        return "conta conectada"
    except Exception:  # noqa: BLE001 - cosmetic only, never blocks the connection
        return "conta conectada"


def _result_page(ok: bool, message: str) -> HTMLResponse:
    """`/oauth/callback` takes unauthenticated, attacker-controllable query
    params (Google's own `error` is reflected here verbatim by design) — the
    message is always HTML-escaped, regardless of the caller (same fix
    applied to `mail/router.py` after the Sprint 1.1 audit — done here from
    the start instead)."""
    color = "#2e7d32" if ok else "#c62828"
    title = "Conectado" if ok else "Falha na conexão"
    return HTMLResponse(
        f"<html><body style='font-family: sans-serif; text-align: center; padding: 4rem;'>"
        f"<h2 style='color: {color}'>{title}</h2><p>{escape(message)}</p>"
        f"<p><a href='/'>Voltar ao painel</a></p></body></html>"
    )
