"""Tests for CoachService — LLM-powered AI coach with mocked Gemini.

Note: google.generativeai can't be imported in this sandbox, so we mock
the entire module chain and config before importing CoachService.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Set required env vars before any bot imports
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("GOOGLE_AI_API_KEY", "test-key")

# Mock google.generativeai to avoid sandbox crypto issue
_genai_mock = MagicMock()
_genai_mock.types = MagicMock()
_genai_mock.types.GenerationConfig = MagicMock
sys.modules["google.generativeai"] = _genai_mock
sys.modules["google.generativeai.types"] = _genai_mock.types

from bot.services.coach_service import CoachService


@pytest.fixture
def mock_conv_repo():
    repo = AsyncMock()
    repo.add_message = AsyncMock()
    repo.get_history = AsyncMock(return_value=[])
    repo.clear_history = AsyncMock()
    return repo


@pytest.fixture
def coach(mock_session, mock_gemini, mock_conv_repo):
    service = CoachService(mock_session, mock_gemini)
    service._conv_repo = mock_conv_repo
    return service


class TestCheckText:
    @pytest.mark.asyncio
    async def test_calls_llm_with_correct_feature(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "Here are your errors..."
        user = make_user(english_level="B1")

        result = await coach.check_text(user, "I have went to store")

        assert result == "Here are your errors..."
        mock_gemini.call.assert_called_once()
        call_kwargs = mock_gemini.call.call_args.kwargs
        assert call_kwargs["feature"] == "coach_check"
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 2000

    @pytest.mark.asyncio
    async def test_uses_user_level(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "OK"
        user = make_user(english_level="A2")

        await coach.check_text(user, "test")

        system = mock_gemini.call.call_args.kwargs["system"]
        assert "A2" in system

    @pytest.mark.asyncio
    async def test_default_level_a1(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "OK"
        user = make_user()
        user.english_level = None

        await coach.check_text(user, "test")

        system = mock_gemini.call.call_args.kwargs["system"]
        assert "A1" in system


class TestExplainWord:
    @pytest.mark.asyncio
    async def test_calls_llm(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "Definition of 'break the ice'..."
        user = make_user()

        result = await coach.explain_word(user, "break the ice")

        assert "Definition" in result
        call_kwargs = mock_gemini.call.call_args.kwargs
        assert call_kwargs["feature"] == "coach_explain"

    @pytest.mark.asyncio
    async def test_word_in_prompt(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "OK"
        user = make_user()

        await coach.explain_word(user, "nevertheless")

        prompt = mock_gemini.call.call_args.kwargs["prompt"]
        assert "nevertheless" in prompt


class TestTranslateText:
    @pytest.mark.asyncio
    async def test_calls_llm(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "Translation: Despite the rain..."
        user = make_user()

        result = await coach.translate_text(user, "Несмотря на дождь")

        assert "Translation" in result
        call_kwargs = mock_gemini.call.call_args.kwargs
        assert call_kwargs["feature"] == "coach_translate"


class TestStartPractice:
    @pytest.mark.asyncio
    async def test_clears_history_and_starts(self, coach, make_user, mock_gemini, mock_conv_repo):
        mock_gemini.call.return_value = "Welcome to the interview!"
        user = make_user()

        result = await coach.start_practice(user, "Job Interview")

        assert result == "Welcome to the interview!"
        mock_conv_repo.clear_history.assert_called_once_with(user.id, "practice")
        mock_conv_repo.add_message.assert_called_once_with(
            user.id, "assistant", "Welcome to the interview!", "practice"
        )

    @pytest.mark.asyncio
    async def test_uses_scenario_in_system_prompt(self, coach, make_user, mock_gemini):
        mock_gemini.call.return_value = "Hi!"
        user = make_user()

        await coach.start_practice(user, "Restaurant")

        system = mock_gemini.call.call_args.kwargs["system"]
        assert "Restaurant" in system


class TestContinuePractice:
    @pytest.mark.asyncio
    async def test_saves_user_message_and_response(self, coach, make_user, mock_gemini, mock_conv_repo):
        mock_gemini.call.return_value = "Good answer! Next question..."
        user = make_user()

        result = await coach.continue_practice(user, "I'd like a table for two", "Restaurant")

        assert result == "Good answer! Next question..."
        assert mock_conv_repo.add_message.call_count == 2
        user_call = mock_conv_repo.add_message.call_args_list[0]
        assert user_call.args == (user.id, "user", "I'd like a table for two", "practice")


class TestEndPractice:
    @pytest.mark.asyncio
    async def test_empty_history(self, coach, make_user, mock_conv_repo):
        mock_conv_repo.get_history.return_value = []
        user = make_user()

        result = await coach.end_practice(user, "Restaurant")

        assert "пуст" in result

    @pytest.mark.asyncio
    async def test_generates_feedback_and_clears(self, coach, make_user, mock_gemini, mock_conv_repo):
        msg1 = MagicMock(role="assistant", content="Welcome!")
        msg2 = MagicMock(role="user", content="Hello, I need a table")
        mock_conv_repo.get_history.return_value = [msg1, msg2]
        mock_gemini.call.return_value = "Great practice! Here's your feedback..."
        user = make_user()

        result = await coach.end_practice(user, "Restaurant")

        assert "feedback" in result
        mock_conv_repo.clear_history.assert_called_once_with(user.id, "practice")
        call_kwargs = mock_gemini.call.call_args.kwargs
        assert call_kwargs["feature"] == "coach_practice_feedback"
