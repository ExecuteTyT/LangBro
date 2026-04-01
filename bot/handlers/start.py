import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.db.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)

router = Router(name="start")


# --- FSM States for onboarding ---
class OnboardingFSM(StatesGroup):
    waiting_name = State()
    waiting_level = State()
    waiting_goal = State()


LEVEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="A1", callback_data="level:A1"),
        InlineKeyboardButton(text="A2", callback_data="level:A2"),
    ],
    [
        InlineKeyboardButton(text="B1", callback_data="level:B1"),
        InlineKeyboardButton(text="B2", callback_data="level:B2"),
    ],
])

GOAL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🗣 Разговорный", callback_data="goal:speaking")],
    [InlineKeyboardButton(text="💼 Для работы", callback_data="goal:work")],
    [InlineKeyboardButton(text="📝 Экзамен", callback_data="goal:exam")],
    [InlineKeyboardButton(text="🌍 Общее развитие", callback_data="goal:general")],
])


# --- /start with deep link ---
@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
):
    payload = command.args or ""

    if not payload.startswith("join_"):
        await cmd_start_plain(message, db_user=db_user)
        return

    invite_code = payload[5:]
    repo = ChallengeRepository(session)
    challenge = await repo.get_by_invite_code(invite_code)

    if not challenge:
        await message.answer("Челлендж не найден 🤷")
        return

    # Check if already a member
    existing = await repo.get_user_challenge(db_user.id, challenge.id)
    if existing:
        await message.answer("Ты уже участвуешь! 💪")
        return

    # Store challenge_id in FSM for after onboarding
    await state.update_data(join_challenge_id=challenge.id)

    if db_user.onboarding_complete:
        # Skip onboarding, join directly
        await _join_challenge(message, session, db_user, challenge)
        await state.clear()
    else:
        # Start onboarding
        await message.answer(
            f"Привет! Добро пожаловать в <b>{challenge.title}</b>! 🎉\n\n"
            "Давай быстро познакомимся. Как к тебе обращаться?"
        )
        await state.set_state(OnboardingFSM.waiting_name)


# --- /start plain ---
@router.message(CommandStart())
async def cmd_start_plain(message: Message, db_user: User, **kwargs):
    name = db_user.display_name or db_user.first_name
    await message.answer(
        f"Йо, {name}! 👋 Я LangBro — твой AI-тренер английского.\n\n"
        "Что я умею:\n"
        "📝 Принимаю отчёты и считаю баллы\n"
        "📊 Веду статистику и рейтинг\n"
        "🔥 Отслеживаю streak\n"
        "📖 Word of the Day каждое утро\n"
        "🧠 Pop Quiz днём\n"
        "⚔️ Weekly Battles\n\n"
        "Напиши /help чтобы увидеть все команды."
    )


# --- /help ---
@router.message(Command("help"))
async def cmd_help(message: Message, **kwargs):
    await message.answer(
        "<b>Команды LangBro</b>\n\n"
        "<b>Группа:</b>\n"
        "/create_challenge — создать челлендж (админ)\n"
        "/launch — отправить приглашение\n"
        "/members — список участников\n"
        "/report <текст> — отправить отчёт\n"
        "/mystats — твоя статистика\n"
        "/leaderboard — рейтинг\n\n"
        "<b>Личка:</b>\n"
        "/report <текст> — отчёт\n"
        "/mystats — подробная статистика\n"
        "/check <текст> — проверка ошибок\n"
        "/practice — ролевой диалог\n"
        "/explain <слово> — объяснение слова\n"
        "/translate <текст> — перевод с разбором\n"
        "/switch — переключить челлендж"
    )


# --- Onboarding FSM handlers ---
@router.message(OnboardingFSM.waiting_name, F.text)
async def onboarding_name(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    name = message.text.strip()[:50]
    db_user.display_name = name
    await session.flush()

    await state.update_data(display_name=name)
    await message.answer(
        f"Приятно, {name}! 🤝\n\nКакой у тебя уровень английского?",
        reply_markup=LEVEL_KB,
    )
    await state.set_state(OnboardingFSM.waiting_level)


@router.callback_query(OnboardingFSM.waiting_level, F.data.startswith("level:"))
async def onboarding_level(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
):
    level = callback.data.split(":")[1]
    db_user.english_level = level

    level_mix = {"A1": 10, "A2": 10, "B1": 30, "B2": 50}
    db_user.bot_language_mix = level_mix.get(level, 10)
    await session.flush()

    await callback.message.edit_text(f"Уровень: <b>{level}</b> ✅")
    await callback.message.answer(
        "Какая у тебя основная цель?",
        reply_markup=GOAL_KB,
    )
    await state.set_state(OnboardingFSM.waiting_goal)
    await callback.answer()


@router.callback_query(OnboardingFSM.waiting_goal, F.data.startswith("goal:"))
async def onboarding_goal(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
):
    goal = callback.data.split(":")[1]
    db_user.learning_goal = goal
    db_user.onboarding_complete = True
    await session.flush()

    goal_labels = {
        "speaking": "🗣 Разговорный",
        "work": "💼 Для работы",
        "exam": "📝 Экзамен",
        "general": "🌍 Общее развитие",
    }
    await callback.message.edit_text(f"Цель: <b>{goal_labels.get(goal, goal)}</b> ✅")

    # Now join the challenge
    fsm_data = await state.get_data()
    challenge_id = fsm_data.get("join_challenge_id")

    if challenge_id:
        repo = ChallengeRepository(session)
        challenge = await repo.get_by_id(challenge_id)
        if challenge:
            await _join_challenge(callback.message, session, db_user, challenge)

    await state.clear()
    await callback.answer()


async def _join_challenge(
    message: Message,
    session: AsyncSession,
    db_user: User,
    challenge,
):
    """Add user to challenge and send confirmation messages."""
    repo = ChallengeRepository(session)

    # Double-check not already joined
    existing = await repo.get_user_challenge(db_user.id, challenge.id)
    if existing:
        await message.answer("Ты уже участвуешь! 💪")
        return

    await repo.add_participant(db_user.id, challenge.id)
    db_user.active_challenge_id = challenge.id
    await session.flush()

    name = db_user.display_name or db_user.first_name

    # Message in DM
    await message.answer(
        f"Ты в деле! 🚀 Добро пожаловать в <b>{challenge.title}</b>!\n\n"
        "Как отправлять отчёт:\n"
        "• В группе: <code>/report Сегодня учил 20 слов...</code>\n"
        "• В личке: <code>/report Сегодня учил 20 слов...</code>\n\n"
        "Пиши отчёт в свободной форме — я разберу.\n"
        "Каждый день = streak 🔥. Let's go!"
    )

    # Try to announce in group chat
    try:
        from aiogram import Bot
        bot: Bot = message.bot  # type: ignore[assignment]
        await bot.send_message(
            challenge.chat_id,
            f"<b>{name}</b> в деле! 🤝",
        )
    except Exception as e:
        logger.warning("Could not send join announcement to group %s: %s", challenge.chat_id, e)
