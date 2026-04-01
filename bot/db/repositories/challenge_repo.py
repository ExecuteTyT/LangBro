from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, UserChallenge


class ChallengeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, challenge_id: int) -> Challenge | None:
        return await self.session.get(Challenge, challenge_id)

    async def get_active_by_chat(self, chat_id: int) -> Challenge | None:
        stmt = select(Challenge).where(
            Challenge.chat_id == chat_id,
            Challenge.status == "active",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_invite_code(self, invite_code: str) -> Challenge | None:
        stmt = select(Challenge).where(Challenge.invite_code == invite_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_active_challenges(
        self, user_id: int
    ) -> list[Challenge]:
        stmt = (
            select(Challenge)
            .join(UserChallenge, UserChallenge.challenge_id == Challenge.id)
            .where(
                UserChallenge.user_id == user_id,
                UserChallenge.status == "active",
                Challenge.status == "active",
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> Challenge:
        challenge = Challenge(**kwargs)
        self.session.add(challenge)
        await self.session.flush()
        return challenge

    async def get_user_challenge(
        self, user_id: int, challenge_id: int
    ) -> UserChallenge | None:
        stmt = select(UserChallenge).where(
            UserChallenge.user_id == user_id,
            UserChallenge.challenge_id == challenge_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_participant(
        self, user_id: int, challenge_id: int
    ) -> UserChallenge:
        uc = UserChallenge(user_id=user_id, challenge_id=challenge_id)
        self.session.add(uc)
        await self.session.flush()
        return uc

    async def get_challenge_members(
        self, challenge_id: int
    ) -> list[UserChallenge]:
        stmt = (
            select(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                UserChallenge.status == "active",
            )
            .order_by(UserChallenge.total_points.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
