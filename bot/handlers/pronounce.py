import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from bot.services.tts_service import TTSService

logger = logging.getLogger(__name__)

router = Router(name="pronounce")


@router.message(Command("pronounce"))
async def cmd_pronounce(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "Напиши слово или фразу:\n"
            "<code>/pronounce nevertheless</code>\n"
            "<code>/pronounce -uk nevertheless</code>"
        )
        return

    text = args[1].strip()
    voice = "us_male"

    # Parse accent flag
    if text.startswith("-uk "):
        voice = "uk_male"
        text = text[4:].strip()
    elif text.startswith("-us "):
        voice = "us_male"
        text = text[4:].strip()
    elif text.startswith("-au "):
        voice = "au_male"
        text = text[4:].strip()

    if not text:
        await message.answer("Укажи слово или фразу после флага акцента.")
        return

    await message.bot.send_chat_action(message.chat.id, "record_voice")

    try:
        tts = TTSService()
        # Single word: slow then normal; phrase: normal speed
        if " " not in text:
            path = await tts.generate_voice(text, voice, rate="-20%")
        else:
            path = await tts.generate_voice(text, voice, rate="+0%")

        await message.answer_voice(FSInputFile(path))
    except Exception as e:
        logger.exception("TTS failed: %s", e)
        await message.answer("Не удалось сгенерировать произношение 🔧")
