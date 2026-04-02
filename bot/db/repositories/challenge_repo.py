from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, User, UserChallenge


class ChallengeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, challenge_id: int) -> Challenge | None:
        return await self.session.get(Challenge, challenge_id)

    async def get_active_by_chat(self, chat_id: int) -> Challenge | None:
        """Get the active or paused challenge for a chat.

        Returns active first; if none, returns paused (so admins can /settings).
        """
        stmt = select(Challenge).where(
            Challenge.chat_id == chat_id,
            Challenge.status.in_(("active", "paused")),
        ).order_by(
            # Prefer active over paused
            Challenge.status.asc()  # "active" < "paused" alphabetically
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_invite_code(self, invite_code: str) -> Challenge | None:
        stmt = select(Challenge).where(Challenge.invite_code == invite_code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_active_challenges(
        self, user_id: int
    ) -> list[Challenge]:
        """Get challenges where user is active. Includes paused challenges."""
        stmt = (
            select(Challenge)
            .join(UserChallenge, UserChallenge.challenge_id == Challenge.id)
            .where(
                UserChallenge.user_id == user_id,
                UserChallenge.status == "active",
                Challenge.status.in_(("active", "paused")),
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

    async def get_member_by_username(
        self, challenge_id: int, username: str
    ) -> UserChallenge | None:
        """Find an active member by Telegram username."""
        stmt = (
            select(UserChallenge)
            .join(User, User.id == UserChallenge.user_id)
            .where(
                UserChallenge.challenge_id == challenge_id,
                UserChallenge.status == "active",
                User.username == username,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def kick_participant(self, uc: UserChallenge) -> None:
        """Set participant status to 'kicked'."""
        uc.status = "kicked"
        await self.session.flush()

    async def update_challenge(self, challenge: Challenge, **kwargs) -> Challenge:
        """Update challenge fields."""
        for key, value in kwargs.items():
            setattr(challenge, key, value)
        await self.session.flush()
        return challenge

    async def get_all_active_user_challenges(self) -> list[UserChallenge]:
        """Get all active user_challenges (for vacation reset)."""
        stmt = select(UserChallenge).where(UserChallenge.status == "active")
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
