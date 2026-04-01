import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, User
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.llm.client import GeminiClient
from bot.services.quiz_service import QuizService

logger = logging.getLogger(__name__)

router = Router(name="quiz")


@router.callback_query(F.data.startswith("quiz:"))
async def quiz_answer_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    challenge: Challenge | None,
):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка формата")
        return

    quiz_id = int(parts[1])
    selected_option = int(parts[2])

    if not challenge:
        await callback.answer("Нет активного челленджа")
        return

    repo = ChallengeRepository(session)
    uc = await repo.get_user_challenge(db_user.id, challenge.id)
    if not uc:
        await callback.answer("Ты не участвуешь в челлендже")
        return

    from bot.db.engine import async_session_factory

    gemini = GeminiClient(session_factory=async_session_factory)
    service = QuizService(session, gemini)

    is_correct, text = await service.handle_answer(
        quiz_id, uc.id, selected_option, challenge
    )
    await callback.answer(text, show_alert=True)
