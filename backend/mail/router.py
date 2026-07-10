"""Gmail connection endpoints — admin-only setup, not a chat surface.

Only `require_admin` can start/inspect/end the OAuth connection
(`/connect`, `/status`, `/disconnect`); `/oauth/callback` is the one route
Google itself calls (a plain browser redirect, no Bearer token possible) —
it authenticates the caller a different way: a short-lived, signed `state`
token minted by `/connect` and validated here (see `auth/jwt.py`).
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import create_oauth_state_token, decode_oauth_state_token
from auth.permissions import require_admin
from database.session import get_db
from mail.schemas import MailConnectResponse, MailStatusResponse
from models.user import User
from providers.mail.base import MailProviderError
from providers.mail.factory import get_mail_provider
from repositories.email_account import EmailAccountRepository
from repositories.user import UserRepository
from services.token_crypto import TokenEncryptionNotConfigured, encrypt_token
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/mail", tags=["mail"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _require_mail_configured() -> None:
    from utils.config import get_settings

    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail integration is not configured (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI)",
        )


@router.get("/connect", response_model=MailConnectResponse, dependencies=[Depends(require_admin)])
async def connect(current_user: Annotated[User, Depends(require_admin)]) -> MailConnectResponse:
    """Returns the Google consent URL for the frontend to redirect the
    admin's browser to — kept as a JSON response (not a 302) so an
    Authorization-header-carrying fetch from the dashboard can call it."""
    _require_mail_configured()
    provider = get_mail_provider()
    state = create_oauth_state_token(current_user.id)
    return MailConnectResponse(authorization_url=provider.authorization_url(state))


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

    user_id = decode_oauth_state_token(state)
    if user_id is None:
        return _result_page(ok=False, message="Sessão de autorização inválida ou expirada. Tente conectar de novo.")

    user = await UserRepository(db).get(user_id)
    if user is None:
        return _result_page(ok=False, message="Usuário não encontrado.")

    provider = get_mail_provider()
    try:
        tokens = await provider.exchange_code(code)
    except MailProviderError as exc:
        logger.error("Gmail OAuth code exchange failed: %s", exc)
        return _result_page(ok=False, message="Não foi possível concluir a autorização com o Google.")

    if not tokens.refresh_token:
        return _result_page(
            ok=False,
            message="O Google não retornou um refresh token. Revogue o acesso anterior em "
            "myaccount.google.com/permissions e tente conectar de novo.",
        )

    try:
        encrypted = encrypt_token(tokens.refresh_token)
    except TokenEncryptionNotConfigured as exc:
        logger.error("Cannot store Gmail refresh token: %s", exc)
        return _result_page(ok=False, message="Armazenamento de credenciais não configurado no servidor.")

    email_address = await _resolve_email_address(provider, tokens.access_token)

    repository = EmailAccountRepository(db)
    existing = await repository.get_by_user(user.id, provider.name)
    if existing is not None:
        await repository.update(
            existing,
            email_address=email_address,
            encrypted_refresh_token=encrypted,
            scopes=tokens.scope.split(),
            connected_at=datetime.now(timezone.utc),
        )
    else:
        await repository.create(
            user_id=user.id,
            provider=provider.name,
            email_address=email_address,
            encrypted_refresh_token=encrypted,
            scopes=tokens.scope.split(),
            connected_at=datetime.now(timezone.utc),
        )

    return _result_page(ok=True, message=f"Conta {email_address} conectada com sucesso.")


@router.get("/status", response_model=MailStatusResponse, dependencies=[Depends(require_admin)])
async def mail_status(
    db: DbSession, current_user: Annotated[User, Depends(require_admin)]
) -> MailStatusResponse:
    account = await EmailAccountRepository(db).get_by_user(current_user.id, get_mail_provider().name)
    if account is None:
        return MailStatusResponse(connected=False)
    return MailStatusResponse(
        connected=True, email_address=account.email_address, connected_at=account.connected_at
    )


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def disconnect(db: DbSession, current_user: Annotated[User, Depends(require_admin)]) -> None:
    repository = EmailAccountRepository(db)
    account = await repository.get_by_user(current_user.id, get_mail_provider().name)
    if account is not None:
        await repository.delete(account)


async def _resolve_email_address(provider, access_token: str) -> str:
    """Best-effort — Gmail's `getProfile` endpoint isn't part of the
    MailProvider contract (only search/get_thread are), so this reads it
    directly; if it fails for any reason, connection still succeeds without
    a friendly label."""
    try:
        import httpx

        from utils.config import get_settings

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{get_settings().gmail_api_base_url}/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json().get("emailAddress", "conta conectada")
    except Exception:  # noqa: BLE001 - cosmetic only, never blocks the connection
        return "conta conectada"


def _result_page(ok: bool, message: str) -> HTMLResponse:
    color = "#2e7d32" if ok else "#c62828"
    title = "Conectado" if ok else "Falha na conexão"
    return HTMLResponse(
        f"<html><body style='font-family: sans-serif; text-align: center; padding: 4rem;'>"
        f"<h2 style='color: {color}'>{title}</h2><p>{message}</p>"
        f"<p><a href='/'>Voltar ao painel</a></p></body></html>"
    )
