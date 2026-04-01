import logging

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repositories.conversation_repo import ConversationRepository
from bot.llm.client import GeminiClient
from bot.llm.prompts.coach import (
    CHECK_SYSTEM,
    CHECK_USER,
    EXPLAIN_SYSTEM,
    EXPLAIN_USER,
    PRACTICE_FEEDBACK_SYSTEM,
    PRACTICE_FEEDBACK_USER,
    PRACTICE_SYSTEM,
    TRANSLATE_SYSTEM,
    TRANSLATE_USER,
)

logger = logging.getLogger(__name__)


class CoachService:
    def __init__(self, session: AsyncSession, llm: GeminiClient) -> None:
        self._session = session
        self._llm = llm
        self._conv_repo = ConversationRepository(session)

    async def check_text(self, user: User, text: str) -> str:
        """Grammar check via LLM. Returns formatted feedback."""
        level = user.english_level or "A1"
        system = CHECK_SYSTEM.format(english_level=level)
        prompt = CHECK_USER.format(english_level=level, user_text=text)

        response = await self._llm.call(
            prompt=prompt,
            system=system,
            feature="coach_check",
            temperature=0.5,
            max_tokens=2000,
        )
        return response.strip()

    async def explain_word(self, user: User, word_or_phrase: str) -> str:
        """Explain a word or phrase."""
        level = user.english_level or "A1"
        system = EXPLAIN_SYSTEM.format(english_level=level)
        prompt = EXPLAIN_USER.format(
            english_level=level, word_or_phrase=word_or_phrase
        )

        response = await self._llm.call(
            prompt=prompt,
            system=system,
            feature="coach_explain",
            temperature=0.5,
            max_tokens=2000,
        )
        return response.strip()

    async def translate_text(self, user: User, text: str) -> str:
        """Translate text with grammar breakdown."""
        level = user.english_level or "A1"
        system = TRANSLATE_SYSTEM.format(english_level=level)
        prompt = TRANSLATE_USER.format(english_level=level, text=text)

        response = await self._llm.call(
            prompt=prompt,
            system=system,
            feature="coach_translate",
            temperature=0.5,
            max_tokens=2000,
        )
        return response.strip()

    async def start_practice(
        self, user: User, scenario: str
    ) -> str:
        """Start a practice dialog. Clears previous history, returns first bot reply."""
        level = user.english_level or "A1"
        await self._conv_repo.clear_history(user.id, "practice")

        system = PRACTICE_SYSTEM.format(scenario=scenario, english_level=level)

        # Opening message from bot to start the scenario
        prompt = (
            f"Начни диалог. Ты — собеседник в сценарии '{scenario}'. "
            "Поприветствуй участника и задай первый вопрос в рамках сценария."
        )

        response = await self._llm.call(
            prompt=prompt,
            system=system,
            feature="coach_practice",
            temperature=0.7,
            max_tokens=500,
        )
        response = response.strip()

        # Save conversation state
        await self._conv_repo.add_message(
            user.id, "assistant", response, "practice"
        )

        return response

    async def continue_practice(
        self, user: User, user_message: str, scenario: str
    ) -> str:
        """Continue the practice dialog."""
        level = user.english_level or "A1"
        system = PRACTICE_SYSTEM.format(scenario=scenario, english_level=level)

        # Save user message
        await self._conv_repo.add_message(
            user.id, "user", user_message, "practice"
        )

        # Build conversation context
        history = await self._conv_repo.get_history(user.id, "practice", limit=20)
        conversation_lines = []
        for msg in history:
            role_label = "Участник" if msg.role == "user" else "Бот"
            conversation_lines.append(f"{role_label}: {msg.content}")

        prompt = (
            "История диалога:\n"
            + "\n".join(conversation_lines)
            + "\n\nПродолжи диалог. Ответь как собеседник в рамках сценария."
        )

        response = await self._llm.call(
            prompt=prompt,
            system=system,
            feature="coach_practice",
            temperature=0.7,
            max_tokens=500,
        )
        response = response.strip()

        # Save bot response
        await self._conv_repo.add_message(
            user.id, "assistant", response, "practice"
        )

        return response

    async def end_practice(self, user: User, scenario: str) -> str:
        """End practice and generate feedback."""
        level = user.english_level or "A1"

        history = await self._conv_repo.get_history(user.id, "practice", limit=30)
        if not history:
            return "Диалог пуст — нечего анализировать."

        conversation_lines = []
        for msg in history:
            role_label = "Участник" if msg.role == "user" else "Бот"
            conversation_lines.append(f"{role_label}: {msg.content}")
        conversation_text = "\n".join(conversation_lines)

        system = PRACTICE_FEEDBACK_SYSTEM.format(english_level=level)
        prompt = PRACTICE_FEEDBACK_USER.format(
            english_level=level,
            scenario=scenario,
            conversation_text=conversation_text,
        )

        response = await self._llm.call(
            prompt=prompt,
            system=system,
            feature="coach_practice_feedback",
            temperature=0.5,
            max_tokens=2000,
        )

        # Clear history after feedback
        await self._conv_repo.clear_history(user.id, "practice")

        return response.strip()
