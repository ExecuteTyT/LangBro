import logging
import random
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, Quiz, QuizAnswer, UserChallenge
from bot.db.repositories.quiz_repo import QuizRepository
from bot.db.repositories.wotd_repo import WotdRepository
from bot.llm.client import GeminiClient
from bot.llm.prompts.quiz_generator import QUIZ_SYSTEM, QUIZ_USER
from bot.llm.schemas import QuizResult

logger = logging.getLogger(__name__)

QUIZ_TYPES = [
    "translation", "grammar", "fill_blank",
    "phrasal_verb", "find_error", "synonym",
]


class QuizService:
    def __init__(self, session: AsyncSession, gemini: GeminiClient):
        self.session = session
        self.repo = QuizRepository(session)
        self.gemini = gemini

    async def generate_and_send(
        self, challenge: Challenge, bot: Bot
    ) -> Quiz:
        quiz_type = random.choice(QUIZ_TYPES)

        # Context for LLM
        wotd_repo = WotdRepository(self.session)
        recent_words = await wotd_repo.get_recent_words(challenge.id, 10)
        recent_topics = await self.repo.get_recent_quiz_topics(challenge.id, 10)

        prompt = QUIZ_USER.format(
            avg_level="B1",
            quiz_type=quiz_type,
            recent_words=", ".join(recent_words) if recent_words else "нет",
            recent_quiz_topics="; ".join(recent_topics[:5]) if recent_topics else "нет",
        )

        data = await self.gemini.call_json(
            prompt=prompt,
            system=QUIZ_SYSTEM,
            feature="quiz",
            temperature=0.7,
            max_tokens=800,
        )
        qr = QuizResult.model_validate(data)

        # Save quiz
        quiz = Quiz(
            challenge_id=challenge.id,
            quiz_type=qr.quiz_type,
            question=qr.question,
            options=qr.options,
            correct_option=qr.correct_option,
            explanation=qr.explanation,
            level=qr.level,
            status="active",
            posted_at=datetime.now(timezone.utc),
        )
        await self.repo.save_quiz(quiz)

        # Build keyboard
        buttons = []
        labels = ["A", "B", "C", "D"]
        for i, option in enumerate(qr.options):
            buttons.append([
                InlineKeyboardButton(
                    text=f"{labels[i]}) {option}",
                    callback_data=f"quiz:{quiz.id}:{i}",
                )
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        msg = await bot.send_message(
            challenge.chat_id,
            f"🧠 <b>Pop Quiz!</b>\n\n{qr.question}",
            reply_markup=kb,
        )
        quiz.message_id = msg.message_id
        await self.session.flush()

        return quiz

    async def handle_answer(
        self,
        quiz_id: int,
        user_challenge_id: int,
        selected_option: int,
        challenge: Challenge,
    ) -> tuple[bool, str]:
        """Process a quiz answer. Returns (is_correct, response_text)."""
        quiz = await self.repo.get_quiz(quiz_id)
        if not quiz or quiz.status != "active":
            return False, "Квиз уже закрыт ⏰"

        # Duplicate check
        existing = await self.repo.get_answer(quiz_id, user_challenge_id)
        if existing:
            return existing.is_correct, "Ты уже отвечал на этот квиз!"

        is_correct = selected_option == quiz.correct_option

        # Check if first correct
        first_correct = await self.repo.get_first_correct(quiz_id)
        is_first = is_correct and first_correct is None

        # Calculate points
        multipliers = challenge.scoring_multipliers or {}
        points = 0
        if is_correct:
            points = multipliers.get("quiz_correct", 15)
            if is_first:
                points += multipliers.get("quiz_speed_bonus", 10)

        answer = QuizAnswer(
            quiz_id=quiz_id,
            user_challenge_id=user_challenge_id,
            selected_option=selected_option,
            is_correct=is_correct,
            is_first_correct=is_first,
            points_earned=points,
        )

        try:
            await self.repo.save_answer(answer)
        except IntegrityError:
            await self.session.rollback()
            return False, "Ты уже отвечал на этот квиз!"

        # Update total points
        if points > 0:
            uc = await self.session.get(UserChallenge, user_challenge_id)
            if uc:
                uc.total_points += points
                await self.session.flush()

        if is_correct:
            bonus = " + 🚀 Speed bonus!" if is_first else ""
            return True, f"✅ Правильно! +{points} pts{bonus}"
        else:
            return False, "❌ Неправильно. Попробуй в следующий раз!"

    async def close_quiz(self, quiz_id: int, bot: Bot) -> None:
        """Close quiz and post results to group."""
        quiz = await self.repo.get_quiz(quiz_id)
        if not quiz or quiz.status != "active":
            return

        await self.repo.close_quiz(quiz_id)
        answers = await self.repo.get_answers_for_quiz(quiz_id)

        correct_answer = quiz.options[quiz.correct_option]
        correct_users = []
        first_name = None

        for ans in answers:
            if ans.is_correct:
                uc = await self.session.get(UserChallenge, ans.user_challenge_id)
                if uc:
                    await self.session.refresh(uc, ["user"])
                    name = uc.user.display_name or uc.user.first_name
                    if ans.is_first_correct:
                        first_name = name
                    correct_users.append(name)

        total_answered = len(answers)
        total_correct = len(correct_users)

        text = (
            f"⏰ <b>Quiz closed!</b>\n\n"
            f"✅ Правильный ответ: <b>{correct_answer}</b>\n"
        )
        if quiz.explanation:
            text += f"💡 {quiz.explanation}\n"
        text += f"\n📊 Ответили: {total_answered}, правильно: {total_correct}"
        if first_name:
            text += f"\n🚀 Быстрее всех: <b>{first_name}</b>"
        if correct_users:
            text += f"\n✅ Правильно ответили: {', '.join(correct_users)}"

        await bot.send_message(quiz.challenge_id, text)

        # Try to edit original message to remove keyboard
        if quiz.message_id:
            try:
                # Need the chat_id from challenge
                from bot.db.repositories.challenge_repo import ChallengeRepository
                challenge_repo = ChallengeRepository(self.session)
                challenge = await challenge_repo.get_by_id(quiz.challenge_id)
                if challenge:
                    await bot.edit_message_reply_markup(
                        chat_id=challenge.chat_id,
                        message_id=quiz.message_id,
                        reply_markup=None,
                    )
            except Exception:
                pass  # Message may have been deleted
