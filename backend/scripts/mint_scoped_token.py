#!/usr/bin/env python3
"""Emite um token com escopo (padrão: somente leitura) para uma integração.

O token é assinado para o dono da instância (um admin ativo) e só alcança o
que o escopo permite (`auth/scopes.py`); ver docs/adr/ADR-0003. A emissão é
deliberadamente um script operado no servidor, não um endpoint da API: quem
consegue emitir já tem acesso ao ambiente e ao banco, e a API não ganha uma
rota que crie credenciais de longa duração.

Uso (dentro do container do backend):

    python scripts/mint_scoped_token.py --email dono@example.com --days 30

O token vai para stdout (e só para lá); mensagens vão para stderr, de modo que
`TOKEN=$(python scripts/mint_scoped_token.py ...)` funciona. A emissão é
auditada na tabela `logs` (usuário, escopo, validade e `jti`, nunca o token).
Para revogar todos os tokens com escopo já emitidos, defina
SCOPED_TOKEN_REVOKED_BEFORE com o timestamp unix atual e reinicie a API.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jwt as pyjwt

from auth.jwt import create_scoped_access_token
from auth.scopes import READ_SCOPE
from database.session import async_session_factory, engine
from models.user import UserRole
from repositories.user import UserRepository
from services.audit import record_log
from utils.config import get_settings


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True, help="e-mail do dono (admin ativo)")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="validade em dias (1 até SCOPED_TOKEN_MAX_DAYS; padrão: 30)",
    )
    parser.add_argument(
        "--scope", default=READ_SCOPE, help=f"escopo do token (padrão: {READ_SCOPE})"
    )
    return parser.parse_args(argv)


async def mint(email: str, days: int, scope: str) -> str:
    """Return a scoped token for the admin `email`, recording the issuance."""
    async with async_session_factory() as session:
        user = await UserRepository(session).get_by_email(email)
        if user is None or not user.is_active or user.role != UserRole.ADMIN:
            raise SystemExit(f"Nenhum admin ativo com o e-mail {email!r}.")

        token = create_scoped_access_token(str(user.id), scope, days)
        # We just signed it ourselves: only reading `jti` back for the audit row.
        claims = pyjwt.decode(token, options={"verify_signature": False})
        await record_log(
            session,
            source="auth:scoped_token",
            message="Scoped token issued",
            level="warning",
            payload={
                "user_id": user.id,
                "scope": scope,
                "expires_days": days,
                "jti": claims["jti"],
            },
        )
        return token


async def _run(args: argparse.Namespace) -> str:
    try:
        return await mint(args.email, args.days, args.scope)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    max_days = get_settings().scoped_token_max_days
    if not 1 <= args.days <= max_days:
        print(f"--days deve estar entre 1 e {max_days}.", file=sys.stderr)
        return 2
    token = asyncio.run(_run(args))
    print(
        f"Token '{args.scope}' emitido para {args.email} (validade: {args.days} dias).",
        file=sys.stderr,
    )
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
