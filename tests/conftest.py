"""Shared fixtures for LangBro tests."""

import os
import sys
from types import SimpleNamespace

import pytest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

# Set required env vars before any bot imports
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("GOOGLE_AI_API_KEY", "test-key")

# Mock google.generativeai to avoid sandbox crypto issue
_genai_mock = MagicMock()
_genai_mock.types = MagicMock()
_genai_mock.types.GenerationConfig = MagicMock
sys.modules.setdefault("google.generativeai", _genai_mock)
sys.modules.setdefault("google.generativeai.types", _genai_mock.types)


@pytest.fixture
def make_user():
    """Factory for User-like objects (SimpleNamespace to avoid ORM issues)."""
    def _make(
        id: int = 1,
        telegram_id: int = 100,
        first_name: str = "Test",
        display_name: str | None = "TestUser",
        english_level: str = "B1",
        learning_goal: str = "general",
        bot_language_mix: int = 30,
        active_challenge_id: int | None = None,
        onboarding_complete: bool = True,
        username: str | None = "testuser",
    ):
        return SimpleNamespace(
            id=id,
            telegram_id=telegram_id,
            first_name=first_name,
            display_name=display_name,
            english_level=english_level,
            learning_goal=learning_goal,
            bot_language_mix=bot_language_mix,
            active_challenge_id=active_challenge_id,
            onboarding_complete=onboarding_complete,
            username=username,
        )
    return _make


@pytest.fixture
def make_challenge():
    """Factory for Challenge-like objects."""
    def _make(
        id: int = 1,
        invite_code: str = "abc12345",
        chat_id: int = -1001234,
        title: str = "Test Challenge",
        status: str = "active",
        schedule_days: list[int] | None = None,
        features_enabled: dict | None = None,
        scoring_multipliers: dict | None = None,
        timezone: str = "Europe/Moscow",
        report_deadline_time: time | None = None,
        digest_time: time | None = None,
        reminder_time: time | None = None,
        wotd_time: time | None = None,
    ):
        return SimpleNamespace(
            id=id,
            invite_code=invite_code,
            chat_id=chat_id,
            title=title,
            status=status,
            schedule_days=schedule_days or [1, 2, 3, 4, 5],
            features_enabled=features_enabled or {
                "daily_digest": True,
                "reminders": True,
                "word_of_day": True,
                "pop_quiz": True,
                "weekly_battles": True,
                "weekly_digest": True,
            },
            scoring_multipliers=scoring_multipliers or {},
            timezone=timezone,
            report_deadline_time=report_deadline_time or time(23, 59),
            digest_time=digest_time or time(22, 0),
            reminder_time=reminder_time or time(20, 0),
            wotd_time=wotd_time or time(8, 0),
        )
    return _make


@pytest.fixture
def make_uc():
    """Factory for UserChallenge-like objects."""
    def _make(
        id: int = 1,
        user_id: int = 1,
        challenge_id: int = 1,
        status: str = "active",
        current_streak: int = 0,
        best_streak: int = 0,
        last_report_date: date | None = None,
        total_points: int = 0,
        total_reports: int = 0,
        total_days_in_challenge: int = 0,
        vacation_until: date | None = None,
        vacation_days_used: int = 0,
        activity_stats: dict | None = None,
    ):
        return SimpleNamespace(
            id=id,
            user_id=user_id,
            challenge_id=challenge_id,
            status=status,
            current_streak=current_streak,
            best_streak=best_streak,
            last_report_date=last_report_date,
            total_points=total_points,
            total_reports=total_reports,
            total_days_in_challenge=total_days_in_challenge,
            vacation_until=vacation_until,
            vacation_days_used=vacation_days_used,
            activity_stats=activity_stats or {
                "speaking_minutes": 0,
                "listening_minutes": 0,
                "reading_minutes": 0,
                "writing_minutes": 0,
                "vocabulary_count": 0,
                "grammar_lessons": 0,
                "app_lessons": 0,
            },
        )
    return _make


@pytest.fixture
def mock_session():
    """Mock AsyncSession for DB operations."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock(return_value=None)
    return session


@pytest.fixture
def mock_gemini():
    """Mock GeminiClient."""
    client = AsyncMock()
    client.call = AsyncMock(return_value="Mocked LLM response")
    client.call_json = AsyncMock(return_value={})
    return client
