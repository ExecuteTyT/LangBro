"""Tests for scoring_service — point calculation logic."""

import pytest
from bot.llm.schemas import ParsedActivity
from bot.services.scoring_service import (
    DEFAULT_MULTIPLIERS,
    calculate_activity_points,
    calculate_report_points,
)


class TestCalculateActivityPoints:
    """Test point calculations for individual activities."""

    def test_speaking_by_duration(self):
        activity = ParsedActivity(category="speaking", duration_minutes=40)
        assert calculate_activity_points(activity) == 80  # 40 * 2

    def test_listening_by_duration(self):
        activity = ParsedActivity(category="listening", duration_minutes=30)
        assert calculate_activity_points(activity) == 30  # 30 * 1

    def test_reading_by_duration(self):
        activity = ParsedActivity(category="reading", duration_minutes=20)
        assert calculate_activity_points(activity) == 30  # 20 * 1.5

    def test_writing_by_duration(self):
        activity = ParsedActivity(category="writing", duration_minutes=15)
        assert calculate_activity_points(activity) == 30  # 15 * 2

    def test_vocabulary_by_count(self):
        activity = ParsedActivity(category="vocabulary", count=15)
        assert calculate_activity_points(activity) == 45  # 15 * 3

    def test_grammar_by_count(self):
        activity = ParsedActivity(category="grammar", count=2)
        assert calculate_activity_points(activity) == 10  # 2 * 5

    def test_app_practice_by_count(self):
        activity = ParsedActivity(category="app_practice", count=3)
        assert calculate_activity_points(activity) == 30  # 3 * 10

    def test_other_no_duration_no_count(self):
        activity = ParsedActivity(category="other")
        assert calculate_activity_points(activity) == 5  # flat 5

    def test_unknown_category_uses_default(self):
        activity = ParsedActivity(category="dancing", duration_minutes=10)
        assert calculate_activity_points(activity) == 50  # 10 * 5 (default)

    def test_custom_multipliers(self):
        activity = ParsedActivity(category="speaking", duration_minutes=10)
        custom = {"speaking": 5}
        assert calculate_activity_points(activity, custom) == 50  # 10 * 5

    def test_duration_takes_precedence_over_count(self):
        activity = ParsedActivity(
            category="vocabulary", duration_minutes=10, count=5
        )
        # duration_minutes is checked first
        assert calculate_activity_points(activity) == 30  # 10 * 3

    def test_zero_duration(self):
        activity = ParsedActivity(category="speaking", duration_minutes=0, count=5)
        # duration_minutes=0 is falsy, falls through to count
        assert calculate_activity_points(activity) == 10  # 5 * 2


class TestCalculateReportPoints:
    """Test total report point calculation."""

    def test_single_activity(self):
        activities = [ParsedActivity(category="speaking", duration_minutes=30)]
        total, per_activity = calculate_report_points(activities)
        assert total == 60
        assert per_activity == [60]

    def test_multiple_activities(self):
        activities = [
            ParsedActivity(category="speaking", duration_minutes=40),
            ParsedActivity(category="vocabulary", count=15),
            ParsedActivity(category="listening", duration_minutes=30),
        ]
        total, per_activity = calculate_report_points(activities)
        assert per_activity == [80, 45, 30]
        assert total == 155

    def test_empty_activities(self):
        total, per_activity = calculate_report_points([])
        assert total == 0
        assert per_activity == []

    def test_custom_multipliers_propagated(self):
        activities = [ParsedActivity(category="speaking", duration_minutes=10)]
        custom = {"speaking": 10}
        total, per_activity = calculate_report_points(activities, custom)
        assert total == 100
        assert per_activity == [100]


class TestDefaultMultipliers:
    """Verify default multiplier values match the spec."""

    def test_all_categories_present(self):
        expected = {
            "speaking", "listening", "reading", "writing",
            "vocabulary", "grammar", "app_practice", "other",
            "wotd_bonus", "quiz_correct", "quiz_speed_bonus",
        }
        assert set(DEFAULT_MULTIPLIERS.keys()) == expected

    def test_speaking_multiplier(self):
        assert DEFAULT_MULTIPLIERS["speaking"] == 2

    def test_vocabulary_multiplier(self):
        assert DEFAULT_MULTIPLIERS["vocabulary"] == 3

    def test_wotd_bonus(self):
        assert DEFAULT_MULTIPLIERS["wotd_bonus"] == 20

    def test_quiz_correct(self):
        assert DEFAULT_MULTIPLIERS["quiz_correct"] == 15

    def test_quiz_speed_bonus(self):
        assert DEFAULT_MULTIPLIERS["quiz_speed_bonus"] == 10
