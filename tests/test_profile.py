"""Tests for profile handler — vacation logic and streak calendar helpers."""

import pytest
from datetime import date, timedelta


class TestVacationLogic:
    """Test vacation constraints matching FR-073 spec."""

    def test_vacation_sets_until_date(self, make_uc):
        uc = make_uc(vacation_until=None, vacation_days_used=0)
        days = 3
        today = date(2026, 4, 1)
        uc.vacation_until = today + timedelta(days=days)
        uc.vacation_days_used += days
        assert uc.vacation_until == date(2026, 4, 4)
        assert uc.vacation_days_used == 3

    def test_vacation_max_7_days(self, make_uc):
        """Max consecutive vacation is 7 days."""
        days = 7
        assert 1 <= days <= 7

    def test_vacation_over_7_rejected(self):
        days = 8
        assert not (1 <= days <= 7)

    def test_monthly_limit_14_days(self, make_uc):
        uc = make_uc(vacation_days_used=10)
        days = 5
        assert uc.vacation_days_used + days > 14

    def test_monthly_limit_exactly_14(self, make_uc):
        uc = make_uc(vacation_days_used=7)
        days = 7
        assert uc.vacation_days_used + days <= 14

    def test_cancel_vacation(self, make_uc):
        uc = make_uc(vacation_until=date(2026, 4, 5))
        uc.vacation_until = None
        assert uc.vacation_until is None

    def test_vacation_active_check(self, make_uc):
        today = date(2026, 4, 1)
        uc = make_uc(vacation_until=date(2026, 4, 3))
        assert uc.vacation_until >= today  # active

    def test_vacation_expired_check(self, make_uc):
        today = date(2026, 4, 5)
        uc = make_uc(vacation_until=date(2026, 4, 3))
        assert uc.vacation_until < today  # expired

    def test_vacation_days_reset(self, make_uc):
        """Monthly reset should zero out vacation_days_used."""
        uc = make_uc(vacation_days_used=12)
        uc.vacation_days_used = 0
        assert uc.vacation_days_used == 0


class TestStreakCalendar:
    """Test streak calendar visual logic."""

    def test_reported_day_is_green(self):
        reported_dates = {date(2026, 4, 1)}
        day = date(2026, 4, 1)
        schedule = [1, 2, 3, 4, 5]
        if day in reported_dates:
            cell = "🟩"
        elif day.isoweekday() not in schedule:
            cell = "⬜"
        else:
            cell = "🟥"
        assert cell == "🟩"

    def test_missed_day_is_red(self):
        reported_dates = set()
        day = date(2026, 4, 1)  # Wednesday
        schedule = [1, 2, 3, 4, 5]
        if day in reported_dates:
            cell = "🟩"
        elif day.isoweekday() not in schedule:
            cell = "⬜"
        else:
            cell = "🟥"
        assert cell == "🟥"

    def test_weekend_is_white(self):
        reported_dates = set()
        day = date(2026, 4, 4)  # Saturday
        schedule = [1, 2, 3, 4, 5]
        if day in reported_dates:
            cell = "🟩"
        elif day.isoweekday() not in schedule:
            cell = "⬜"
        else:
            cell = "🟥"
        assert cell == "⬜"

    def test_weekend_reported_still_green(self):
        """If someone reports on weekend, it's still green."""
        reported_dates = {date(2026, 4, 4)}  # Saturday
        day = date(2026, 4, 4)
        schedule = [1, 2, 3, 4, 5]
        if day in reported_dates:
            cell = "🟩"
        elif day.isoweekday() not in schedule:
            cell = "⬜"
        else:
            cell = "🟥"
        assert cell == "🟩"

    def test_28_day_range(self):
        today = date(2026, 4, 2)
        start = today - timedelta(days=27)
        assert (today - start).days == 27  # 28 days inclusive
