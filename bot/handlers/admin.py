"""Admin commands: /settings, /kick, /pause, /resume."""

import logging
from datetime import time as dt_time

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, User
from bot.db.repositories.challenge_repo import ChallengeRepository

logger = logging.getLogger(__name__)

router = Router(name="admin")


# --- FSM for text input settings ---
class SettingsFSM(StatesGroup):
    waiting_time_input = State()


# --- Helpers ---

async def _check_admin(message: Message) -> bool:
    """Check if sender is group admin. Returns True if admin."""
    if message.chat.type == "private":
        return True  # In DM — we check challenge ownership later
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ("creator", "administrator")


def _settings_main_kb(challenge: Challenge) -> InlineKeyboardMarkup:
    """Build the main settings menu keyboard."""
    status_emoji = "✅" if challenge.status == "active" else "⏸"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📅 Расписание дней", callback_data="settings:schedule"
        )],
        [InlineKeyboardButton(
            text="⏰ Времена (дайджест, WotD...)", callback_data="settings:times"
        )],
        [InlineKeyboardButton(
            text="🔧 Фичи (вкл/выкл)", callback_data="settings:features"
        )],
        [InlineKeyboardButton(
            text=f"{status_emoji} Статус: {challenge.status}",
            callback_data="settings:status",
        )],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="settings:close")],
    ])


WEEKDAY_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}


def _schedule_kb(schedule_days: list[int]) -> InlineKeyboardMarkup:
    """Build the schedule days toggle keyboard."""
    buttons = []
    row = []
    for day_num in range(1, 8):
        is_on = day_num in schedule_days
        emoji = "✅" if is_on else "⬜"
        row.append(InlineKeyboardButton(
            text=f"{emoji} {WEEKDAY_NAMES[day_num]}",
            callback_data=f"sched_toggle:{day_num}",
        ))
        if len(row) == 4 or day_num == 7:
            buttons.append(row)
            row = []
    buttons.append([
        InlineKeyboardButton(text="Пн-Пт", callback_data="sched_preset:weekdays"),
        InlineKeyboardButton(text="Каждый день", callback_data="sched_preset:daily"),
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


FEATURE_LABELS = {
    "daily_digest": "📊 Daily Digest",
    "reminders": "⏰ Напоминания",
    "word_of_day": "📖 Word of the Day",
    "pop_quiz": "🧠 Pop Quiz",
    "weekly_battles": "⚔️ Weekly Battles",
    "weekly_digest": "📈 Weekly Digest",
}


def _features_kb(features: dict) -> InlineKeyboardMarkup:
    """Build the features toggle keyboard."""
    buttons = []
    for key, label in FEATURE_LABELS.items():
        is_on = features.get(key, True)
        emoji = "✅" if is_on else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {label}",
            callback_data=f"feat_toggle:{key}",
        )])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


TIME_SETTINGS = {
    "digest_time": "📊 Digest",
    "reminder_time": "⏰ Напоминание",
    "wotd_time": "📖 WotD",
    "report_deadline_time": "📝 Дедлайн отчёта",
}


def _times_kb(challenge: Challenge) -> InlineKeyboardMarkup:
    """Build the times settings keyboard."""
    buttons = []
    for field, label in TIME_SETTINGS.items():
        current = getattr(challenge, field)
        time_str = current.strftime("%H:%M") if current else "—"
        buttons.append([InlineKeyboardButton(
            text=f"{label}: {time_str}",
            callback_data=f"time_edit:{field}",
        )])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ---- /settings ----
@router.message(Command("settings"))
async def cmd_settings(
    message: Message,
    session: AsyncSession,
    challenge: Challenge | None,
    **kwargs,
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return

    if not await _check_admin(message):
        await message.answer("Только админы могут менять настройки ✋")
        return

    await message.answer(
        f"⚙️ <b>Настройки: {challenge.title}</b>",
        reply_markup=_settings_main_kb(challenge),
    )


# ---- Main menu navigation ----
@router.callback_query(F.data == "settings:main")
async def settings_main(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Челлендж не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚙️ <b>Настройки: {challenge.title}</b>",
        reply_markup=_settings_main_kb(challenge),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:close")
async def settings_close(callback: CallbackQuery, **kwargs):
    await callback.message.edit_text("⚙️ Настройки закрыты.")
    await callback.answer()


# ---- Schedule days ----
@router.callback_query(F.data == "settings:schedule")
async def settings_schedule(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    schedule = challenge.schedule_days or [1, 2, 3, 4, 5]
    await callback.message.edit_text(
        "📅 <b>Расписание</b>\n\n"
        "Выбери дни, в которые участники должны отчитываться.\n"
        "Streak не сбрасывается в выходные дни.",
        reply_markup=_schedule_kb(schedule),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sched_toggle:"))
async def sched_toggle(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    day_num = int(callback.data.split(":")[1])
    schedule = list(challenge.schedule_days or [1, 2, 3, 4, 5])

    if day_num in schedule:
        schedule.remove(day_num)
    else:
        schedule.append(day_num)
        schedule.sort()

    if not schedule:
        await callback.answer("Нужно выбрать хотя бы один день!", show_alert=True)
        return

    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, schedule_days=schedule)

    await callback.message.edit_reply_markup(reply_markup=_schedule_kb(schedule))
    await callback.answer()


@router.callback_query(F.data.startswith("sched_preset:"))
async def sched_preset(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    preset = callback.data.split(":")[1]
    if preset == "weekdays":
        schedule = [1, 2, 3, 4, 5]
    else:
        schedule = [1, 2, 3, 4, 5, 6, 7]

    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, schedule_days=schedule)

    await callback.message.edit_reply_markup(reply_markup=_schedule_kb(schedule))
    await callback.answer(f"Расписание обновлено: {'Пн-Пт' if preset == 'weekdays' else 'Каждый день'}")


# ---- Features toggle ----
@router.callback_query(F.data == "settings:features")
async def settings_features(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    features = challenge.features_enabled or {}
    await callback.message.edit_text(
        "🔧 <b>Фичи</b>\n\nВключай/выключай функции челленджа:",
        reply_markup=_features_kb(features),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("feat_toggle:"))
async def feat_toggle(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    feature_key = callback.data.split(":")[1]
    features = dict(challenge.features_enabled or {})
    features[feature_key] = not features.get(feature_key, True)

    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, features_enabled=features)

    status = "включено ✅" if features[feature_key] else "выключено ❌"
    label = FEATURE_LABELS.get(feature_key, feature_key)
    await callback.message.edit_reply_markup(reply_markup=_features_kb(features))
    await callback.answer(f"{label}: {status}")


# ---- Times settings ----
@router.callback_query(F.data == "settings:times")
async def settings_times(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    await callback.message.edit_text(
        "⏰ <b>Времена</b> (часовой пояс: MSK)\n\n"
        "Нажми на время, чтобы изменить:",
        reply_markup=_times_kb(challenge),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("time_edit:"))
async def time_edit_start(
    callback: CallbackQuery, state: FSMContext, **kwargs
):
    field = callback.data.split(":")[1]
    label = TIME_SETTINGS.get(field, field)

    await state.update_data(time_field=field)
    await state.set_state(SettingsFSM.waiting_time_input)

    await callback.message.edit_text(
        f"⏰ <b>Изменить: {label}</b>\n\n"
        "Отправь новое время в формате <b>ЧЧ:ММ</b>\n"
        "Например: <code>20:30</code>\n\n"
        "Отправь <code>отмена</code> чтобы вернуться."
    )
    await callback.answer()


@router.message(SettingsFSM.waiting_time_input, F.text)
async def time_edit_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    challenge: Challenge | None,
    **kwargs,
):
    text = message.text.strip().lower()

    if text in ("отмена", "cancel"):
        await state.clear()
        if challenge:
            await message.answer(
                f"⚙️ <b>Настройки: {challenge.title}</b>",
                reply_markup=_settings_main_kb(challenge),
            )
        else:
            await message.answer("Отменено.")
        return

    # Parse HH:MM
    try:
        parts = text.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        new_time = dt_time(hour, minute)
    except (ValueError, IndexError):
        await message.answer("Неверный формат. Отправь время как <b>ЧЧ:ММ</b>, например <code>20:30</code>")
        return

    data = await state.get_data()
    field = data.get("time_field")

    if not challenge or not field:
        await state.clear()
        await message.answer("Ошибка — начни заново через /settings")
        return

    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, **{field: new_time})
    await state.clear()

    label = TIME_SETTINGS.get(field, field)
    await message.answer(
        f"✅ {label} обновлено: <b>{new_time.strftime('%H:%M')}</b> MSK\n\n"
        f"⚙️ <b>Настройки: {challenge.title}</b>",
        reply_markup=_settings_main_kb(challenge),
    )


# ---- Challenge status (pause/resume) ----
@router.callback_query(F.data == "settings:status")
async def settings_status(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return

    if challenge.status == "active":
        buttons = [[
            InlineKeyboardButton(text="⏸ Поставить на паузу", callback_data="challenge_pause"),
        ]]
    else:
        buttons = [[
            InlineKeyboardButton(text="▶️ Возобновить", callback_data="challenge_resume"),
        ]]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:main")])

    await callback.message.edit_text(
        f"Статус челленджа: <b>{challenge.status}</b>\n\n"
        "Пауза:\n"
        "• Streak НЕ сбрасывается\n"
        "• Бот НЕ отправляет напоминания и дайджесты\n"
        "• Участники НЕ могут отправлять отчёты",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "challenge_pause")
async def challenge_pause(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, status="paused")
    await callback.message.edit_text(
        f"⏸ Челлендж <b>{challenge.title}</b> на паузе.\n\n"
        "Streak заморожен. Бот не шлёт напоминания.\n"
        "Для возобновления: /settings → Статус → Возобновить"
    )
    await callback.answer("Челлендж на паузе")


@router.callback_query(F.data == "challenge_resume")
async def challenge_resume(
    callback: CallbackQuery, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await callback.answer("Нет челленджа", show_alert=True)
        return
    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, status="active")
    await callback.message.edit_text(
        f"▶️ Челлендж <b>{challenge.title}</b> возобновлён!\n\n"
        "Бот снова в деле. Let's go! 💪"
    )
    await callback.answer("Челлендж возобновлён")


# ---- /pause and /resume commands (shortcuts) ----
@router.message(Command("pause"))
async def cmd_pause(
    message: Message, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return
    if not await _check_admin(message):
        await message.answer("Только админы могут ставить на паузу ✋")
        return

    if challenge.status == "paused":
        await message.answer("Челлендж уже на паузе. Используй /resume для возобновления.")
        return

    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, status="paused")
    await message.answer(
        f"⏸ <b>{challenge.title}</b> на паузе.\n\n"
        "Streak заморожен, напоминания отключены.\n"
        "Для возобновления: /resume"
    )


@router.message(Command("resume"))
async def cmd_resume(
    message: Message, session: AsyncSession, challenge: Challenge | None, **kwargs
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return
    if not await _check_admin(message):
        await message.answer("Только админы могут возобновлять ✋")
        return

    if challenge.status == "active":
        await message.answer("Челлендж уже активен!")
        return

    repo = ChallengeRepository(session)
    await repo.update_challenge(challenge, status="active")
    await message.answer(
        f"▶️ <b>{challenge.title}</b> снова в деле!\n\n"
        "Streak продолжается, all systems go 💪"
    )


# ---- /kick ----
@router.message(Command("kick"))
async def cmd_kick(
    message: Message, session: AsyncSession, challenge: Challenge | None, db_user: User, **kwargs
):
    if not challenge:
        await message.answer("Нет активного челленджа.")
        return

    if not await _check_admin(message):
        await message.answer("Только админы могут кикать ✋")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Укажи username: <code>/kick @username</code>")
        return

    username = args[1].strip().lstrip("@")

    repo = ChallengeRepository(session)
    uc = await repo.get_member_by_username(challenge.id, username)

    if not uc:
        await message.answer(f"Участник @{username} не найден в этом челлендже.")
        return

    await session.refresh(uc, ["user"])
    name = uc.user.display_name or uc.user.first_name

    # Don't allow kicking yourself
    if uc.user.telegram_id == message.from_user.id:
        await message.answer("Нельзя кикнуть самого себя 🤔")
        return

    await repo.kick_participant(uc)

    # If this was user's active challenge, clear it
    if uc.user.active_challenge_id == challenge.id:
        uc.user.active_challenge_id = None
        await session.flush()

    await message.answer(
        f"👋 <b>{name}</b> (@{username}) удалён из челленджа.\n"
        "Статистика сохранена в архиве."
    )
