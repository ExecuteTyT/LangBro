import logging
from datetime import datetime, timezone, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, User, UserChallenge
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.db.repositories.stats_repo import StatsRepository

logger = logging.getLogger(__name__)

router = Router(name="stats")


@router.message(Command("mystats"))
async def cmd_mystats(
    message: Message,
    session: AsyncSession,
    db_user: User,
    challenge: Challenge | None,
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return

    repo = ChallengeRepository(session)
    uc = await repo.get_user_challenge(db_user.id, challenge.id)
    if not uc:
        await message.answer("Ты не участвуешь в этом челлендже.")
        return

    name = db_user.display_name or db_user.first_name

    # Calculate rank
    from bot.db.repositories.report_repo import ReportRepository
    report_repo = ReportRepository(session)
    rank, total = await report_repo.get_user_rank(challenge.id, uc.id)

    # Build activity distribution
    stats = uc.activity_stats or {}
    act_lines = []
    act_map = [
        ("🗣 Speaking", "speaking_minutes", "мин"),
        ("👂 Listening", "listening_minutes", "мин"),
        ("📖 Reading", "reading_minutes", "мин"),
        ("✍️ Writing", "writing_minutes", "мин"),
        ("📚 Vocabulary", "vocabulary_count", "слов"),
        ("📝 Grammar", "grammar_lessons", "уроков"),
        ("📱 Apps", "app_lessons", "уроков"),
    ]
    for label, key, unit in act_map:
        val = stats.get(key, 0)
        if val:
            act_lines.append(f"   {label}: {val} {unit}")

    activity_block = "\n".join(act_lines) if act_lines else "   Пока нет данных"

    # Streak record?
    streak_note = ""
    if uc.current_streak == uc.best_streak and uc.current_streak > 1:
        streak_note = " (рекорд! 🏆)"

    text = (
        f"📊 <b>Твоя статистика, {name}</b>\n"
        f"📌 <i>{challenge.title}</i>\n\n"
        f"🔥 Текущий streak: <b>{uc.current_streak}</b> дней{streak_note}\n"
        f"🏆 Лучший streak: <b>{uc.best_streak}</b> дней\n"
        f"✅ Отчётов: <b>{uc.total_reports}</b>\n\n"
        f"💰 Всего баллов: <b>{uc.total_points} pts</b>\n"
        f"📊 Позиция: #{rank} из {total}\n\n"
        f"📈 Активности (всего):\n{activity_block}"
    )
    await message.answer(text)


@router.message(Command("leaderboard"))
async def cmd_leaderboard(
    message: Message,
    session: AsyncSession,
    challenge: Challenge | None,
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return

    stats_repo = StatsRepository(session)
    members = await stats_repo.get_leaderboard(challenge.id)

    if not members:
        await message.answer("Пока нет участников.")
        return

    lines = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, uc in enumerate(members, 1):
        await session.refresh(uc, ["user"])
        user = uc.user
        name = user.display_name or user.first_name
        medal = medals.get(i, f"{i}.")
        streak = f" 🔥{uc.current_streak}" if uc.current_streak > 0 else ""
        lines.append(f"{medal} <b>{name}</b> — {uc.total_points} pts{streak}")

    text = (
        f"🏆 <b>Рейтинг — {challenge.title}</b>\n\n"
        + "\n".join(lines)
    )
    await message.answer(text)
