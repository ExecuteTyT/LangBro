import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.engine import async_session_factory
from bot.db.models import User
from bot.llm.client import GeminiClient
from bot.services.coach_service import CoachService
from bot.services.tts_service import TTSService

logger = logging.getLogger(__name__)

router = Router(name="coach")


# --- FSM for /practice ---
class PracticeFSM(StatesGroup):
    in_dialog = State()


SCENARIO_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="💼 Job Interview", callback_data="practice:job_interview")],
    [InlineKeyboardButton(text="🍕 Ordering at a Restaurant", callback_data="practice:restaurant")],
    [InlineKeyboardButton(text="🎉 Small Talk at a Party", callback_data="practice:small_talk")],
    [InlineKeyboardButton(text="📊 Business Meeting", callback_data="practice:business_meeting")],
    [InlineKeyboardButton(text="✈️ At the Airport", callback_data="practice:airport")],
    [InlineKeyboardButton(text="✏️ Свой сценарий", callback_data="practice:custom")],
])

SCENARIO_LABELS = {
    "job_interview": "Job Interview",
    "restaurant": "Ordering at a Restaurant",
    "small_talk": "Small Talk at a Party",
    "business_meeting": "Business Meeting",
    "airport": "At the Airport",
}


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a long message into chunks respecting Telegram limit."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        # Try to split at newline
        idx = text.rfind("\n", 0, max_len)
        if idx < max_len // 2:
            idx = max_len
        parts.append(text[:idx])
        text = text[idx:].lstrip("\n")
    return parts


# ---- /check ----
@router.message(Command("check"))
async def cmd_check(message: Message, db_user: User, session: AsyncSession, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "Напиши текст для проверки:\n"
            "<code>/check I have went to the store yesterday</code>"
        )
        return

    text = args[1].strip()
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        llm = GeminiClient(session_factory=async_session_factory)
        service = CoachService(session, llm)
        result = await service.check_text(db_user, text)

        for part in _split_message(result):
            await message.answer(part)

        # TTS: pronounce corrected version (best effort)
        try:
            tts = TTSService()
            # Extract text after "Исправленная версия" or just use original if not found
            voice_path = await tts.generate_voice(text, "us_male", rate="+0%")
            await message.answer_voice(FSInputFile(voice_path))
        except Exception:
            pass  # TTS is optional for /check

    except Exception as e:
        logger.exception("Coach /check error: %s", e)
        await message.answer("Сорри, что-то пошло не так. Попробуй через минуту 🔧")


# ---- /explain ----
@router.message(Command("explain"))
async def cmd_explain(message: Message, db_user: User, session: AsyncSession, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "Напиши слово или фразу:\n"
            "<code>/explain nevertheless</code>\n"
            "<code>/explain break the ice</code>"
        )
        return

    word = args[1].strip()
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        llm = GeminiClient(session_factory=async_session_factory)
        service = CoachService(session, llm)
        result = await service.explain_word(db_user, word)

        for part in _split_message(result):
            await message.answer(part)

        # TTS: pronounce the word/phrase
        try:
            tts = TTSService()
            rate = "-20%" if " " not in word else "+0%"
            voice_path = await tts.generate_voice(word, "us_male", rate=rate)
            await message.answer_voice(FSInputFile(voice_path))
        except Exception:
            pass  # TTS is optional

    except Exception as e:
        logger.exception("Coach /explain error: %s", e)
        await message.answer("Сорри, что-то пошло не так. Попробуй через минуту 🔧")


# ---- /translate ----
@router.message(Command("translate"))
async def cmd_translate(message: Message, db_user: User, session: AsyncSession, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "Напиши текст для перевода:\n"
            "<code>/translate Несмотря на дождь, мы пошли гулять</code>\n"
            "<code>/translate It's raining cats and dogs</code>"
        )
        return

    text = args[1].strip()
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        llm = GeminiClient(session_factory=async_session_factory)
        service = CoachService(session, llm)
        result = await service.translate_text(db_user, text)

        for part in _split_message(result):
            await message.answer(part)

    except Exception as e:
        logger.exception("Coach /translate error: %s", e)
        await message.answer("Сорри, что-то пошло не так. Попробуй через минуту 🔧")


# ---- /practice ----
@router.message(Command("practice"))
async def cmd_practice(message: Message, state: FSMContext, **kwargs):
    current_state = await state.get_state()
    if current_state == PracticeFSM.in_dialog.state:
        await message.answer(
            "У тебя уже активный диалог. Отправь /done чтобы закончить "
            "и получить разбор, или просто продолжай писать."
        )
        return

    await message.answer(
        "🎭 <b>Practice Mode</b>\n\n"
        "Выбери сценарий для разговорной практики:",
        reply_markup=SCENARIO_KB,
    )


@router.callback_query(F.data.startswith("practice:"))
async def practice_scenario_chosen(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
    **kwargs,
):
    scenario_key = callback.data.split(":")[1]

    if scenario_key == "custom":
        await callback.message.edit_text(
            "✏️ Напиши свой сценарий (одним сообщением):\n"
            "Например: <i>Buying a car at a dealership</i>"
        )
        await state.update_data(waiting_custom_scenario=True)
        await state.set_state(PracticeFSM.in_dialog)
        await callback.answer()
        return

    scenario = SCENARIO_LABELS.get(scenario_key, scenario_key)
    await callback.message.edit_text(f"🎭 Сценарий: <b>{scenario}</b>")
    await callback.answer()

    await _start_practice(callback.message, state, db_user, session, scenario)


async def _start_practice(
    message: Message,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
    scenario: str,
):
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        llm = GeminiClient(session_factory=async_session_factory)
        service = CoachService(session, llm)
        reply = await service.start_practice(db_user, scenario)

        await state.update_data(
            practice_scenario=scenario,
            waiting_custom_scenario=False,
        )
        await state.set_state(PracticeFSM.in_dialog)

        stop_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Закончить и получить разбор", callback_data="practice_done")],
        ])

        await message.answer(reply, reply_markup=stop_kb)

    except Exception as e:
        logger.exception("Practice start error: %s", e)
        await state.clear()
        await message.answer("Сорри, что-то пошло не так. Попробуй через минуту 🔧")


# Handle messages during practice dialog
@router.message(PracticeFSM.in_dialog, F.text)
async def practice_message(
    message: Message,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
    **kwargs,
):
    data = await state.get_data()

    # Handle custom scenario input
    if data.get("waiting_custom_scenario"):
        scenario = message.text.strip()[:200]
        await _start_practice(message, state, db_user, session, scenario)
        return

    scenario = data.get("practice_scenario", "Free conversation")
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        llm = GeminiClient(session_factory=async_session_factory)
        service = CoachService(session, llm)
        reply = await service.continue_practice(db_user, message.text, scenario)

        stop_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Закончить и получить разбор", callback_data="practice_done")],
        ])

        await message.answer(reply, reply_markup=stop_kb)

    except Exception as e:
        logger.exception("Practice continue error: %s", e)
        await message.answer("Сорри, что-то пошло не так. Попробуй через минуту 🔧")


# /done command to end practice
@router.message(Command("done"), PracticeFSM.in_dialog)
async def cmd_done(
    message: Message,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
    **kwargs,
):
    await _end_practice(message, state, db_user, session)


# Inline button to end practice
@router.callback_query(F.data == "practice_done")
async def practice_done_callback(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
    **kwargs,
):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _end_practice(callback.message, state, db_user, session)


async def _end_practice(
    message: Message,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
):
    data = await state.get_data()
    scenario = data.get("practice_scenario", "Free conversation")
    await state.clear()

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        llm = GeminiClient(session_factory=async_session_factory)
        service = CoachService(session, llm)
        feedback = await service.end_practice(db_user, scenario)

        await message.answer("🏁 <b>Practice завершён!</b>\n\nРазбор:")

        for part in _split_message(feedback):
            await message.answer(part)

    except Exception as e:
        logger.exception("Practice feedback error: %s", e)
        await message.answer("Сорри, не удалось сгенерировать разбор 🔧")
