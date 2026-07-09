from sqlalchemy import select

from models.church import ChurchMember
from repositories.base import SQLAlchemyRepository


class ChurchMemberRepository(SQLAlchemyRepository[ChurchMember]):
    model = ChurchMember

    async def search_by_name(self, query: str, limit: int = 5) -> list[ChurchMember]:
        statement = select(ChurchMember).where(ChurchMember.name.ilike(f"%{query}%")).limit(limit)
        return list((await self.session.execute(statement)).scalars().all())
