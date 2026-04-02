"""User profile commands: /profile, /switch, /streak, /vacation."""

import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, User, UserChallenge
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.handlers.common import challenge_choose_kb

logger = logging.getLogger(__name__)

router = Router(name="profile")

LEVEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="A1", callback_data="prof_level:A1"),
        InlineKeyboardButton(text="A2", callback_data="prof_level:A2"),
    ],
    [
        InlineKeyboardButton(text="B1", callback_data="prof_level:B1"),
        InlineKeyboardButton(text="B2", callback_data="prof_level:B2"),
    ],
])

GOAL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🗣 Разговорный", callback_data="prof_goal:speaking")],
    [InlineKeyboardButton(text="💼 Для работы", callback_data="prof_goal:work")],
    [InlineKeyboardButton(text="📝 Экзамен", callback_data="prof_goal:exam")],
    [InlineKeyboardButton(text="🌍 Общее развитие", callback_data="prof_goal:general")],
])

GOAL_LABELS = {
    "speaking": "🗣 Разговорный",
    "work": "💼 Для работы",
    "exam": "📝 Экзамен",
    "general": "🌍 Общее развитие",
}


# ---- /profile ----
@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User, **kwargs):
    name = db_user.display_name or db_user.first_name
    level = db_user.english_level or "не указан"
    goal = GOAL_LABELS.get(db_user.learning_goal or "", db_user.learning_goal or "не указана")

    edit_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить уровень", callback_data="prof_edit:level")],
        [InlineKeyboardButton(text="🎯 Изменить цель", callback_data="prof_edit:goal")],
    ])

    await message.answer(
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: <b>{name}</b>\n"
        f"Уровень: <b>{level}</b>\n"
        f"Цель: <b>{goal}</b>\n\n"
        "Нажми кнопку, чтобы обновить:",
        reply_markup=edit_kb,
    )


@router.callback_query(F.data == "prof_edit:level")
async def prof_edit_level(callback: CallbackQuery, **kwargs):
    await callback.message.edit_text(
        "Выбери свой текущий уровень английского:",
        reply_markup=LEVEL_KB,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prof_level:"))
async def prof_set_level(
    callback: CallbackQuery, db_user: User, session: AsyncSession, **kwargs
):
    level = callback.data.split(":")[1]
    db_user.english_level = level

    level_mix = {"A1": 10, "A2": 10, "B1": 30, "B2": 50}
    db_user.bot_language_mix = level_mix.get(level, 10)
    await session.flush()

    await callback.message.edit_text(f"✅ Уровень обновлён: <b>{level}</b>")
    await callback.answer()


@router.callback_query(F.data == "prof_edit:goal")
async def prof_edit_goal(callback: CallbackQuery, **kwargs):
    await callback.message.edit_text(
        "Выбери свою основную цель:",
        reply_markup=GOAL_KB,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prof_goal:"))
async def prof_set_goal(
    callback: CallbackQuery, db_user: User, session: AsyncSession, **kwargs
):
    goal = callback.data.split(":")[1]
    db_user.learning_goal = goal
    await session.flush()

    label = GOAL_LABELS.get(goal, goal)
    await callback.message.edit_text(f"✅ Цель обновлена: <b>{label}</b>")
    await callback.answer()


# ---- /switch ----
@router.message(Command("switch"))
async def cmd_switch(message: Message, db_user: User, session: AsyncSession, **kwargs):
    if message.chat.type != "private":
        await message.answer("Команда /switch работает только в личке.")
        return

    repo = ChallengeRepository(session)
    challenges = await repo.get_user_active_challenges(db_user.id)

    if not challenges:
        await message.answer("У тебя нет активных челленджей.")
        return

    if len(challenges) == 1:
        c = challenges[0]
        db_user.active_challenge_id = c.id
        await session.flush()
        await message.answer(f"📌 Активный челлендж: <b>{c.title}</b>")
        return

    await message.answer(
        "В каком челлендже работаем?",
        reply_markup=challenge_choose_kb(challenges),
    )


@router.callback_query(F.data.startswith("switch_challenge:"))
async def switch_challenge_callback(
    callback: CallbackQuery, db_user: User, session: AsyncSession, **kwargs
):
    challenge_id = int(callback.data.split(":")[1])
    repo = ChallengeRepository(session)
    challenge = await repo.get_by_id(challenge_id)

    if not challenge:
        await callback.answer("Челлендж не найден", show_alert=True)
        return

    db_user.active_challenge_id = challenge.id
    await session.flush()

    await callback.message.edit_text(f"📌 Активный челлендж: <b>{challenge.title}</b>")
    await callback.answer()


# ---- /streak ----
@router.message(Command("streak"))
async def cmd_streak(
    message: Message,
    session: AsyncSession,
    db_user: User,
    challenge: Challenge | None,
    **kwargs,
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return

    repo = ChallengeRepository(session)
    uc = await repo.get_user_challenge(db_user.id, challenge.id)
    if not uc:
        await message.answer("Ты не участвуешь в этом челлендже.")
        return

    # Build streak calendar — last 28 days (4 weeks)
    today = datetime.now(timezone.utc).date()
    schedule_days = challenge.schedule_days or [1, 2, 3, 4, 5]

    # Get all reports for user in this challenge for the last 28 days
    from bot.db.repositories.report_repo import ReportRepository
    report_repo = ReportRepository(session)

    # We need report dates — get them from daily_reports
    from sqlalchemy import select
    from bot.db.models import DailyReport
    start_date = today - timedelta(days=27)
    stmt = (
        select(DailyReport.report_date)
        .where(
            DailyReport.user_challenge_id == uc.id,
            DailyReport.report_date >= start_date,
            DailyReport.report_date <= today,
        )
    )
    result = await session.execute(stmt)
    reported_dates = {row[0] for row in result.all()}

    # Build calendar grid
    name = db_user.display_name or db_user.first_name
    lines = [
        f"🔥 <b>Streak Calendar — {name}</b>\n",
        f"Текущий streak: <b>{uc.current_streak}</b> дней",
        f"Лучший streak: <b>{uc.best_streak}</b> дней\n",
        "Пн Вт Ср Чт Пт Сб Вс",
    ]

    # Align to Monday of the start week
    start_weekday = start_date.isoweekday()  # 1=Mon
    week_start = start_date - timedelta(days=start_weekday - 1)

    current = week_start
    while current <= today:
        week_cells = []
        for dow in range(7):  # Mon-Sun
            day = current + timedelta(days=dow)
            if day < start_date or day > today:
                week_cells.append("  ")
            elif day.isoweekday() not in schedule_days:
                week_cells.append("⬜")  # non-scheduled day
            elif day in reported_dates:
                week_cells.append("🟩")  # reported
            else:
                week_cells.append("🟥")  # missed
        lines.append(" ".join(week_cells))
        current += timedelta(days=7)

    lines.append("")
    lines.append("🟩 отчёт  🟥 пропуск  ⬜ выходной")

    # Vacation info
    if uc.vacation_until and uc.vacation_until >= today:
        remaining = (uc.vacation_until - today).days
        lines.append(f"\n🏖 На каникулах (осталось {remaining} дн.)")

    await message.answer("\n".join(lines))


# ---- /vacation ----
@router.message(Command("vacation"))
async def cmd_vacation(
    message: Message,
    session: AsyncSession,
    db_user: User,
    challenge: Challenge | None,
    **kwargs,
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return

    repo = ChallengeRepository(session)
    uc = await repo.get_user_challenge(db_user.id, challenge.id)
    if not uc:
        await message.answer("Ты не участвуешь в этом челлендже.")
        return

    today = datetime.now(timezone.utc).date()

    # Check if already on vacation
    if uc.vacation_until and uc.vacation_until >= today:
        remaining = (uc.vacation_until - today).days
        await message.answer(
            f"🏖 Ты уже на каникулах до <b>{uc.vacation_until.strftime('%d.%m')}</b> "
            f"(осталось {remaining} дн.)\n\n"
            "Отправь <code>/vacation 0</code> чтобы выйти раньше."
        )
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer(
            "🏖 <b>Каникулы</b>\n\n"
            "Streak замораживается, бот тебя не тегает.\n\n"
            "Использование: <code>/vacation 3</code> (от 1 до 7 дней)\n"
            f"Использовано в этом месяце: {uc.vacation_days_used}/14 дней\n\n"
            "Отмена каникул: <code>/vacation 0</code>"
        )
        return

    days = int(args[1].strip())

    # Cancel vacation
    if days == 0:
        if uc.vacation_until and uc.vacation_until >= today:
            uc.vacation_until = None
            await session.flush()
            await message.answer("✅ Каникулы отменены. Welcome back! 💪")
        else:
            await message.answer("Ты не на каникулах.")
        return

    # Validate days
    if days < 1 or days > 7:
        await message.answer("Максимум 7 дней подряд. Укажи от 1 до 7.")
        return

    # Check monthly limit (reset if new month)
    if uc.vacation_until:
        # If last vacation was in a different month, reset counter
        if uc.vacation_until.month != today.month or uc.vacation_until.year != today.year:
            uc.vacation_days_used = 0

    if uc.vacation_days_used + days > 14:
        remaining_budget = 14 - uc.vacation_days_used
        await message.answer(
            f"Лимит: 14 дней каникул в месяц.\n"
            f"Использовано: {uc.vacation_days_used}/14\n"
            f"Осталось: {remaining_budget} дн."
        )
        return

    # Set vacation
    uc.vacation_until = today + timedelta(days=days)
    uc.vacation_days_used += days
    await session.flush()

    name = db_user.display_name or db_user.first_name
    await message.answer(
        f"🏖 <b>{name}</b> уходит на каникулы!\n\n"
        f"Период: до <b>{uc.vacation_until.strftime('%d.%m')}</b> ({days} дн.)\n"
        f"Streak заморожен: {uc.current_streak} 🔥\n"
        f"Использовано в этом месяце: {uc.vacation_days_used}/14 дней"
    )
