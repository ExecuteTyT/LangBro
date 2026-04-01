from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import BattlePair, WeeklyBattle


class BattleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_battle(
        self, challenge_id: int, week_start: date, week_end: date
    ) -> WeeklyBattle:
        battle = WeeklyBattle(
            challenge_id=challenge_id,
            week_start=week_start,
            week_end=week_end,
        )
        self.session.add(battle)
        await self.session.flush()
        return battle

    async def get_active_battle(
        self, challenge_id: int
    ) -> WeeklyBattle | None:
        stmt = select(WeeklyBattle).where(
            WeeklyBattle.challenge_id == challenge_id,
            WeeklyBattle.status == "active",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_pair(
        self, battle_id: int, player1_id: int, player2_id: int | None
    ) -> BattlePair:
        pair = BattlePair(
            battle_id=battle_id,
            player1_id=player1_id,
            player2_id=player2_id,
        )
        self.session.add(pair)
        await self.session.flush()
        return pair

    async def get_battle_pairs(self, battle_id: int) -> list[BattlePair]:
        stmt = (
            select(BattlePair)
            .where(BattlePair.battle_id == battle_id)
            .order_by(BattlePair.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def close_battle(self, battle_id: int) -> None:
        battle = await self.session.get(WeeklyBattle, battle_id)
        if battle:
            battle.status = "completed"
            await self.session.flush()
