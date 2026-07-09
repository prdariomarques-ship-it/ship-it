from datetime import datetime

from sqlalchemy import delete

from models.refresh_token import RefreshToken
from repositories.base import SQLAlchemyRepository


class RefreshTokenRepository(SQLAlchemyRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self.find_one(token_hash=token_hash)

    async def revoke(self, token: RefreshToken, at: datetime) -> None:
        token.revoked_at = at
        await self.session.commit()

    async def purge_expired(self, user_id: int, now: datetime) -> None:
        """Delete this user's expired tokens (revoked ones stay until expiry, for audit)."""
        await self.session.execute(
            delete(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.expires_at <= now)
            # Skip ORM in-session evaluation: SQLite round-trips naive datetimes,
            # which the evaluator can't compare against the aware bound value.
            .execution_options(synchronize_session=False)
        )
