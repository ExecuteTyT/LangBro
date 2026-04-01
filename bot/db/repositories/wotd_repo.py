from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import WordOfTheDay


class WotdRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_today_wotd(
        self, challenge_id: int, today: date
    ) -> WordOfTheDay | None:
        stmt = select(WordOfTheDay).where(
            WordOfTheDay.challenge_id == challenge_id,
            WordOfTheDay.posted_date == today,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_wotd(self, wotd: WordOfTheDay) -> WordOfTheDay:
        self.session.add(wotd)
        await self.session.flush()
        return wotd

    async def get_recent_words(
        self, challenge_id: int, limit: int = 30
    ) -> list[str]:
        stmt = (
            select(WordOfTheDay.word)
            .where(WordOfTheDay.challenge_id == challenge_id)
            .order_by(WordOfTheDay.posted_date.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_last_n_words(
        self, challenge_id: int, n: int = 5
    ) -> list[str]:
        return await self.get_recent_words(challenge_id, limit=n)
