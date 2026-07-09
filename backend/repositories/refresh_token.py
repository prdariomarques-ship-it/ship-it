from datetime import datetime

from models.refresh_token import RefreshToken
from repositories.base import SQLAlchemyRepository


class RefreshTokenRepository(SQLAlchemyRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return await self.find_one(token_hash=token_hash)

    async def revoke(self, token: RefreshToken, at: datetime) -> None:
        token.revoked_at = at
        await self.session.commit()
