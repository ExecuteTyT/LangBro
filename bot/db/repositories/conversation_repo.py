from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ConversationHistory


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_message(
        self, user_id: int, role: str, content: str, feature: str
    ) -> ConversationHistory:
        entry = ConversationHistory(
            user_id=user_id, role=role, content=content, feature=feature
        )
        self._s.add(entry)
        await self._s.flush()
        return entry

    async def get_history(
        self, user_id: int, feature: str, limit: int = 20
    ) -> list[ConversationHistory]:
        result = await self._s.execute(
            select(ConversationHistory)
            .where(
                ConversationHistory.user_id == user_id,
                ConversationHistory.feature == feature,
            )
            .order_by(ConversationHistory.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def clear_history(self, user_id: int, feature: str) -> None:
        await self._s.execute(
            delete(ConversationHistory).where(
                ConversationHistory.user_id == user_id,
                ConversationHistory.feature == feature,
            )
        )
        await self._s.flush()
