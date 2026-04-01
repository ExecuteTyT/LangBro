import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, User, UserChallenge
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.llm.client import GeminiClient
from bot.services.report_service import ReportService

logger = logging.getLogger(__name__)

router = Router(name="report")


@router.message(Command("report"))
async def cmd_report(
    message: Message,
    session: AsyncSession,
    db_user: User,
    challenge: Challenge | None,
):
    if not challenge:
        await message.answer(
            "Нет активного челленджа. Присоединись через ссылку-приглашение!"
        )
        return

    if challenge.status == "paused":
        await message.answer(
            f"⏸ Челлендж <b>{challenge.title}</b> на паузе.\n"
            "Отчёты временно не принимаются. Свяжись с админом."
        )
        return

    # Extract report text
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "Напиши отчёт после команды:\n"
            "<code>/report Сегодня учил 20 слов и смотрел TED Talk</code>"
        )
        return

    raw_text = args[1].strip()

    # Get user_challenge
    repo = ChallengeRepository(session)
    uc = await repo.get_user_challenge(db_user.id, challenge.id)
    if not uc:
        await message.answer("Ты не участвуешь в этом челлендже. Присоединись сначала!")
        return

    # Process
    await message.bot.send_chat_action(message.chat.id, "typing")

    from bot.db.engine import async_session_factory

    gemini = GeminiClient(session_factory=async_session_factory)
    service = ReportService(session, gemini)

    try:
        source = "private" if message.chat.type == "private" else "group"
        response = await service.process_report(
            raw_text=raw_text,
            user=db_user,
            uc=uc,
            challenge=challenge,
            message_id=message.message_id,
            source=source,
        )
        await message.answer(response)
    except Exception as e:
        logger.exception("Report processing failed: %s", e)
        await message.answer(
            "Сорри, что-то пошло не так. Попробуй через минуту 🔧"
        )
