import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import FSInputFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, UserChallenge, User, WordOfTheDay
from bot.db.repositories.wotd_repo import WotdRepository
from bot.llm.client import GeminiClient
from bot.llm.prompts.wotd_generator import WOTD_SYSTEM, WOTD_USER
from bot.llm.schemas import WotdResult
from bot.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class WotdService:
    def __init__(self, session: AsyncSession, gemini: GeminiClient):
        self.session = session
        self.repo = WotdRepository(session)
        self.gemini = gemini

    async def _get_avg_level(self, challenge_id: int) -> str:
        stmt = (
            select(User.english_level)
            .join(UserChallenge, UserChallenge.user_id == User.id)
            .where(
                UserChallenge.challenge_id == challenge_id,
                UserChallenge.status == "active",
            )
        )
        result = await self.session.execute(stmt)
        levels = list(result.scalars().all())
        if not levels:
            return "B1"
        level_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4}
        avg = sum(level_order.get(l, 3) for l in levels) / len(levels)
        for name, val in sorted(level_order.items(), key=lambda x: x[1]):
            if avg <= val + 0.5:
                return name
        return "B1"

    async def generate_and_send(
        self, challenge: Challenge, bot: Bot
    ) -> None:
        today = datetime.now(timezone.utc).date()

        # Idempotency check
        existing = await self.repo.get_today_wotd(challenge.id, today)
        if existing:
            logger.info("WotD already posted for challenge %s today", challenge.id)
            return

        # Prepare LLM context
        recent_words = await self.repo.get_recent_words(challenge.id, 30)
        last_5 = await self.repo.get_last_n_words(challenge.id, 5)
        avg_level = await self._get_avg_level(challenge.id)

        prompt = WOTD_USER.format(
            avg_level=avg_level,
            used_words_list=", ".join(recent_words) if recent_words else "нет",
            last_5_words=", ".join(last_5) if last_5 else "нет",
        )

        data = await self.gemini.call_json(
            prompt=prompt,
            system=WOTD_SYSTEM,
            feature="wotd",
            temperature=0.7,
            max_tokens=800,
        )
        wotd = WotdResult.model_validate(data)

        # Save to DB
        wotd_row = WordOfTheDay(
            challenge_id=challenge.id,
            word=wotd.word,
            pronunciation=wotd.pronunciation,
            translation=wotd.translation,
            level=wotd.level,
            examples=[e if isinstance(e, dict) else {"en": str(e)} for e in wotd.examples],
            related_words=wotd.related_words,
            posted_date=today,
        )
        await self.repo.save_wotd(wotd_row)

        # Format message
        examples_text = ""
        for ex in wotd.examples[:2]:
            en = ex.get("en", "") if isinstance(ex, dict) else str(ex)
            ru = ex.get("ru", "") if isinstance(ex, dict) else ""
            examples_text += f'• "{en}"'
            if ru:
                examples_text += f"\n  {ru}"
            examples_text += "\n"

        related = ", ".join(wotd.related_words[:4]) if wotd.related_words else ""

        text = (
            "🌅 <b>Good morning, bros!</b>\n\n"
            f"📖 <b>Word of the Day:</b> <code>{wotd.word}</code>\n"
            f"🔊 {wotd.pronunciation}\n"
            f"📝 {wotd.translation}\n"
        )
        if wotd.part_of_speech:
            text += f"🏷 {wotd.part_of_speech}\n"
        text += f"\n💡 <b>Примеры:</b>\n{examples_text}"
        if related:
            text += f"\n🎯 Связано: {related}\n"
        if wotd.usage_tip:
            text += f"\n💬 <i>{wotd.usage_tip}</i>\n"
        if wotd.challenge_task:
            text += f"\n📌 <b>Challenge:</b> {wotd.challenge_task}"

        msg = await bot.send_message(challenge.chat_id, text)
        wotd_row.message_id = msg.message_id
        await self.session.flush()

        # TTS voice
        try:
            tts = TTSService()
            first_example_en = ""
            if wotd.examples:
                ex = wotd.examples[0]
                first_example_en = ex.get("en", "") if isinstance(ex, dict) else str(ex)

            if first_example_en:
                voice_path = await tts.generate_wotd_voice(
                    wotd.word, first_example_en
                )
            else:
                voice_path = await tts.generate_voice(wotd.word, rate="-30%")

            await bot.send_voice(challenge.chat_id, FSInputFile(voice_path))
        except Exception as e:
            logger.warning("TTS failed for WotD '%s': %s", wotd.word, e)
