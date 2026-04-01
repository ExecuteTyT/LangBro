from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Quiz, QuizAnswer


class QuizRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_quiz(self, quiz: Quiz) -> Quiz:
        self.session.add(quiz)
        await self.session.flush()
        return quiz

    async def get_quiz(self, quiz_id: int) -> Quiz | None:
        return await self.session.get(Quiz, quiz_id)

    async def get_open_quizzes(self, challenge_id: int) -> list[Quiz]:
        stmt = select(Quiz).where(
            Quiz.challenge_id == challenge_id,
            Quiz.status == "active",
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_answer(self, answer: QuizAnswer) -> QuizAnswer:
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def get_answer(
        self, quiz_id: int, user_challenge_id: int
    ) -> QuizAnswer | None:
        stmt = select(QuizAnswer).where(
            QuizAnswer.quiz_id == quiz_id,
            QuizAnswer.user_challenge_id == user_challenge_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_first_correct(self, quiz_id: int) -> QuizAnswer | None:
        stmt = (
            select(QuizAnswer)
            .where(
                QuizAnswer.quiz_id == quiz_id,
                QuizAnswer.is_correct == True,
            )
            .order_by(QuizAnswer.answered_at.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_answers_for_quiz(self, quiz_id: int) -> list[QuizAnswer]:
        stmt = (
            select(QuizAnswer)
            .where(QuizAnswer.quiz_id == quiz_id)
            .order_by(QuizAnswer.answered_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def close_quiz(self, quiz_id: int) -> None:
        quiz = await self.get_quiz(quiz_id)
        if quiz and quiz.status == "active":
            quiz.status = "closed"
            quiz.closed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def get_recent_quiz_topics(
        self, challenge_id: int, limit: int = 10
    ) -> list[str]:
        stmt = (
            select(Quiz.question)
            .where(Quiz.challenge_id == challenge_id)
            .order_by(Quiz.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stale_active_quizzes(self, max_age_minutes: int = 30) -> list[Quiz]:
        """Find active quizzes older than max_age_minutes (for startup cleanup)."""
        cutoff = datetime.now(timezone.utc).replace(
            second=0, microsecond=0
        )
        stmt = select(Quiz).where(
            Quiz.status == "active",
            Quiz.posted_at != None,
            Quiz.posted_at < cutoff,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
