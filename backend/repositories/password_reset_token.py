from datetime import datetime

from sqlalchemy import delete, update

from models.password_reset_token import PasswordResetToken
from repositories.base import SQLAlchemyRepository


class PasswordResetTokenRepository(SQLAlchemyRepository[PasswordResetToken]):
    model = PasswordResetToken

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        return await self.find_one(token_hash=token_hash)

    async def mark_used(self, token: PasswordResetToken, at: datetime) -> None:
        token.used_at = at
        await self.session.commit()

    async def invalidate_unused_for_user(self, user_id: int, at: datetime) -> None:
        """Issuing a new reset token supersedes every previous one that
        hasn't been redeemed yet -- only the latest token for a user is ever
        valid. Same idiom as RefreshTokenRepository.revoke_all_for_user."""
        await self.session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=at)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()

    async def purge_expired(self, user_id: int, now: datetime) -> None:
        """Same hygiene as RefreshTokenRepository.purge_expired -- delete this
        user's expired tokens so the table stays small."""
        await self.session.execute(
            delete(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.expires_at <= now,
            )
            .execution_options(synchronize_session=False)
        )
