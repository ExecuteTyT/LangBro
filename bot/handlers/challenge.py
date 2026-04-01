import logging
import secrets
import string

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from bot.db.models import Challenge, User, UserChallenge
from bot.db.repositories.challenge_repo import ChallengeRepository

logger = logging.getLogger(__name__)

router = Router(name="challenge")


def _generate_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


# --- /create_challenge ---
@router.message(Command("create_challenge"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_create_challenge(
    message: Message,
    session: AsyncSession,
    db_user: User,
):
    # Check if sender is admin
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("creator", "administrator"):
        await message.answer("Только админы могут создавать челленджи ✋")
        return

    repo = ChallengeRepository(session)

    # Check if chat already has an active challenge
    existing = await repo.get_active_by_chat(message.chat.id)
    if existing:
        await message.answer(
            f"В этом чате уже есть активный челлендж: <b>{existing.title}</b>\n"
            "Используй /launch чтобы пригласить участников."
        )
        return

    # Extract title from command args or use default
    args = message.text.split(maxsplit=1)
    title = args[1].strip() if len(args) > 1 else "Английский челлендж"

    invite_code = _generate_invite_code()

    challenge = await repo.create(
        invite_code=invite_code,
        chat_id=message.chat.id,
        title=title,
        created_by=db_user.id,
    )
    await session.flush()

    bot_info = await message.bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=join_{invite_code}"

    await message.answer(
        f"🎯 Челлендж <b>{title}</b> создан!\n\n"
        f"📋 Код: <code>{invite_code}</code>\n"
        f"🔗 Ссылка: {deep_link}\n\n"
        "Используй /launch чтобы отправить приглашение для участников."
    )


# --- /launch ---
@router.message(Command("launch"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_launch(
    message: Message,
    session: AsyncSession,
    challenge: Challenge | None,
):
    if not challenge:
        await message.answer("Сначала создай челлендж: /create_challenge <название>")
        return

    # Check admin
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("creator", "administrator"):
        await message.answer("Только админы могут запускать /launch ✋")
        return

    bot_info = await message.bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=join_{challenge.invite_code}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Присоединиться", url=deep_link)]
    ])

    await message.answer(
        f"🎯 <b>{challenge.title}</b>\n\n"
        "Готов прокачать английский? Жми кнопку и начинай! 👇\n\n"
        "Что тебя ждёт:\n"
        "📝 Ежедневные отчёты → баллы\n"
        "🔥 Streak за стабильность\n"
        "📊 Рейтинг и статистика\n"
        "📖 Word of the Day\n"
        "🧠 Pop Quiz\n"
        "⚔️ Weekly Battles",
        reply_markup=kb,
    )


# --- /members ---
@router.message(Command("members"))
async def cmd_members(
    message: Message,
    session: AsyncSession,
    challenge: Challenge | None,
):
    if not challenge:
        await message.answer("Нет активного челленджа в этом чате.")
        return

    repo = ChallengeRepository(session)
    members = await repo.get_challenge_members(challenge.id)

    if not members:
        await message.answer("Пока никто не присоединился 🤷")
        return

    # Load user data for each member
    lines = []
    for i, uc in enumerate(members, 1):
        await session.refresh(uc, ["user"])
        user = uc.user
        name = user.display_name or user.first_name
        streak = f"🔥{uc.current_streak}" if uc.current_streak > 0 else ""
        level = user.english_level
        points = f"{uc.total_points} pts"
        lines.append(f"{i}. <b>{name}</b> ({level}) — {points} {streak}")

    text = (
        f"👥 <b>{challenge.title}</b> — участники ({len(members)}):\n\n"
        + "\n".join(lines)
    )
    await message.answer(text)
