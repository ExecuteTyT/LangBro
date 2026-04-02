"""Tests for Pydantic LLM schemas — validation and edge cases."""

import pytest
from pydantic import ValidationError

from bot.llm.schemas import ParsedActivity, ReportParseResult, WotdResult, QuizResult


class TestParsedActivity:
    """Test ParsedActivity model."""

    def test_minimal(self):
        a = ParsedActivity(category="speaking")
        assert a.category == "speaking"
        assert a.duration_minutes is None
        assert a.count is None
        assert a.description is None
        assert a.details is None

    def test_with_duration(self):
        a = ParsedActivity(category="listening", duration_minutes=30, description="Podcast")
        assert a.duration_minutes == 30
        assert a.description == "Podcast"

    def test_with_count(self):
        a = ParsedActivity(category="vocabulary", count=15)
        assert a.count == 15

    def test_from_dict(self):
        data = {"category": "writing", "duration_minutes": 20, "details": "essay"}
        a = ParsedActivity(**data)
        assert a.category == "writing"
        assert a.details == "essay"


class TestReportParseResult:
    """Test ReportParseResult model."""

    def test_empty(self):
        r = ReportParseResult()
        assert r.activities == []
        assert r.word_of_day_used is False
        assert r.raw_summary == ""

    def test_with_activities(self):
        r = ReportParseResult(
            activities=[
                ParsedActivity(category="speaking", duration_minutes=30),
                ParsedActivity(category="vocabulary", count=10),
            ],
            word_of_day_used=True,
            raw_summary="Good day",
        )
        assert len(r.activities) == 2
        assert r.word_of_day_used is True

    def test_from_json_dict(self):
        """Simulate LLM JSON output."""
        data = {
            "activities": [
                {"category": "speaking", "duration_minutes": 40},
                {"category": "vocabulary", "count": 15},
            ],
            "word_of_day_used": True,
            "raw_summary": "Созвон + слова",
        }
        r = ReportParseResult(**data)
        assert r.activities[0].category == "speaking"
        assert r.activities[1].count == 15


class TestWotdResult:
    """Test WotdResult model."""

    def test_minimal(self):
        w = WotdResult(word="hello")
        assert w.word == "hello"
        assert w.level == "B1"
        assert w.examples == []
        assert w.related_words == []

    def test_full(self):
        w = WotdResult(
            word="nevertheless",
            pronunciation="/ˌnevəðəˈles/",
            translation="тем не менее",
            level="B2",
            part_of_speech="adverb",
            examples=[{"en": "Nevertheless, we tried.", "ru": "Тем не менее, мы попробовали."}],
            related_words=["however", "although"],
            usage_tip="Formal",
            challenge_task="Use it today",
        )
        assert w.word == "nevertheless"
        assert len(w.examples) == 1
        assert len(w.related_words) == 2

    def test_word_required(self):
        with pytest.raises(ValidationError):
            WotdResult()


class TestQuizResult:
    """Test QuizResult model."""

    def test_valid(self):
        q = QuizResult(
            quiz_type="grammar",
            question="Choose the correct form",
            options=["has", "have", "had", "having"],
            correct_option=0,
            explanation="Present perfect",
            level="B1",
        )
        assert q.quiz_type == "grammar"
        assert len(q.options) == 4
        assert q.correct_option == 0

    def test_too_few_options(self):
        with pytest.raises(ValidationError):
            QuizResult(
                quiz_type="grammar",
                question="Q",
                options=["a", "b"],
                correct_option=0,
            )

    def test_too_many_options(self):
        with pytest.raises(ValidationError):
            QuizResult(
                quiz_type="grammar",
                question="Q",
                options=["a", "b", "c", "d", "e"],
                correct_option=0,
            )

    def test_correct_option_out_of_range(self):
        with pytest.raises(ValidationError):
            QuizResult(
                quiz_type="grammar",
                question="Q",
                options=["a", "b", "c", "d"],
                correct_option=5,
            )

    def test_correct_option_negative(self):
        with pytest.raises(ValidationError):
            QuizResult(
                quiz_type="grammar",
                question="Q",
                options=["a", "b", "c", "d"],
                correct_option=-1,
            )

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            QuizResult(quiz_type="grammar")
