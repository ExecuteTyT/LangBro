"""Tests for streak_service — streak calculation and vacation logic."""

import pytest
from datetime import date, timedelta

from bot.services.streak_service import is_next_scheduled_day, update_streak, _was_on_vacation


class TestIsNextScheduledDay:
    """Test next-scheduled-day detection."""

    def test_consecutive_weekdays_mon_tue(self):
        assert is_next_scheduled_day(
            date(2026, 3, 30),  # Mon
            date(2026, 3, 31),  # Tue
            [1, 2, 3, 4, 5],
        )

    def test_friday_to_monday_skips_weekend(self):
        assert is_next_scheduled_day(
            date(2026, 3, 27),  # Fri
            date(2026, 3, 30),  # Mon
            [1, 2, 3, 4, 5],
        )

    def test_friday_to_saturday_not_scheduled(self):
        assert not is_next_scheduled_day(
            date(2026, 3, 27),  # Fri
            date(2026, 3, 28),  # Sat
            [1, 2, 3, 4, 5],
        )

    def test_friday_to_tuesday_is_gap(self):
        assert not is_next_scheduled_day(
            date(2026, 3, 27),  # Fri
            date(2026, 3, 31),  # Tue
            [1, 2, 3, 4, 5],
        )

    def test_every_day_schedule(self):
        assert is_next_scheduled_day(
            date(2026, 3, 28),  # Sat
            date(2026, 3, 29),  # Sun
            [1, 2, 3, 4, 5, 6, 7],
        )

    def test_empty_schedule_consecutive(self):
        assert is_next_scheduled_day(
            date(2026, 3, 30),
            date(2026, 3, 31),
            [],
        )

    def test_empty_schedule_gap(self):
        assert not is_next_scheduled_day(
            date(2026, 3, 30),
            date(2026, 4, 1),
            [],
        )

    def test_custom_schedule_mon_wed_fri(self):
        assert is_next_scheduled_day(
            date(2026, 3, 30),  # Mon
            date(2026, 4, 1),   # Wed
            [1, 3, 5],          # Mon, Wed, Fri
        )

    def test_custom_schedule_wed_to_fri(self):
        assert is_next_scheduled_day(
            date(2026, 4, 1),   # Wed
            date(2026, 4, 3),   # Fri
            [1, 3, 5],
        )

    def test_same_day_not_next(self):
        assert not is_next_scheduled_day(
            date(2026, 3, 30),
            date(2026, 3, 30),
            [1, 2, 3, 4, 5],
        )


class TestUpdateStreak:
    """Test streak updates including vacation handling."""

    def test_first_report_starts_streak(self, make_uc):
        uc = make_uc(current_streak=0, best_streak=0, last_report_date=None)
        update_streak(uc, date(2026, 3, 30), [1, 2, 3, 4, 5])
        assert uc.current_streak == 1
        assert uc.best_streak == 1
        assert uc.last_report_date == date(2026, 3, 30)

    def test_consecutive_day_increments(self, make_uc):
        uc = make_uc(current_streak=5, best_streak=5, last_report_date=date(2026, 3, 30))
        update_streak(uc, date(2026, 3, 31), [1, 2, 3, 4, 5])
        assert uc.current_streak == 6
        assert uc.best_streak == 6

    def test_same_day_no_change(self, make_uc):
        uc = make_uc(current_streak=5, best_streak=5, last_report_date=date(2026, 3, 30))
        update_streak(uc, date(2026, 3, 30), [1, 2, 3, 4, 5])
        assert uc.current_streak == 5
        assert uc.best_streak == 5

    def test_gap_resets_streak(self, make_uc):
        uc = make_uc(current_streak=10, best_streak=10, last_report_date=date(2026, 3, 30))
        # Skip Tue, report on Wed
        update_streak(uc, date(2026, 4, 1), [1, 2, 3, 4, 5])
        assert uc.current_streak == 1
        assert uc.best_streak == 10  # best unchanged

    def test_weekend_skip_continues_streak(self, make_uc):
        uc = make_uc(current_streak=5, best_streak=5, last_report_date=date(2026, 3, 27))  # Fri
        update_streak(uc, date(2026, 3, 30), [1, 2, 3, 4, 5])  # Mon
        assert uc.current_streak == 6

    def test_best_streak_updated(self, make_uc):
        uc = make_uc(current_streak=9, best_streak=9, last_report_date=date(2026, 3, 30))
        update_streak(uc, date(2026, 3, 31), [1, 2, 3, 4, 5])
        assert uc.current_streak == 10
        assert uc.best_streak == 10

    def test_best_streak_not_lowered(self, make_uc):
        uc = make_uc(current_streak=3, best_streak=15, last_report_date=date(2026, 3, 25))
        # Gap → reset to 1, but best stays 15
        update_streak(uc, date(2026, 3, 30), [1, 2, 3, 4, 5])
        assert uc.current_streak == 1
        assert uc.best_streak == 15


class TestVacationStreak:
    """Test vacation-aware streak logic."""

    def test_vacation_covers_gap(self, make_uc):
        """Streak should continue if gap is covered by vacation."""
        uc = make_uc(
            current_streak=10,
            best_streak=10,
            last_report_date=date(2026, 3, 27),  # Fri
            vacation_until=date(2026, 4, 1),       # vacation until Wed
        )
        # Report on Thu (after vacation)
        update_streak(uc, date(2026, 4, 2), [1, 2, 3, 4, 5])
        assert uc.current_streak == 11  # continues!
        assert uc.vacation_until is None  # cleared

    def test_vacation_day_after_return(self, make_uc):
        """Report the day after vacation_until still counts as covered."""
        uc = make_uc(
            current_streak=5,
            best_streak=5,
            last_report_date=date(2026, 3, 30),   # Mon
            vacation_until=date(2026, 4, 1),        # vacation until Wed
        )
        # Report on Thu (vacation_until + 1)
        update_streak(uc, date(2026, 4, 2), [1, 2, 3, 4, 5])
        assert uc.current_streak == 6

    def test_vacation_expired_resets_streak(self, make_uc):
        """If report is way after vacation ended, streak resets."""
        uc = make_uc(
            current_streak=5,
            best_streak=5,
            last_report_date=date(2026, 3, 27),    # Fri
            vacation_until=date(2026, 3, 30),       # vacation until Mon
        )
        # Report on Thu (3 days after vacation ended)
        update_streak(uc, date(2026, 4, 2), [1, 2, 3, 4, 5])
        assert uc.current_streak == 1  # reset

    def test_no_vacation_normal_gap(self, make_uc):
        """Without vacation, gap resets streak."""
        uc = make_uc(
            current_streak=5,
            best_streak=5,
            last_report_date=date(2026, 3, 27),
            vacation_until=None,
        )
        update_streak(uc, date(2026, 4, 2), [1, 2, 3, 4, 5])
        assert uc.current_streak == 1

    def test_vacation_cleared_after_report(self, make_uc):
        """vacation_until should be cleared when report comes after vacation."""
        uc = make_uc(
            current_streak=5,
            best_streak=5,
            last_report_date=date(2026, 3, 30),
            vacation_until=date(2026, 3, 31),
        )
        update_streak(uc, date(2026, 4, 1), [1, 2, 3, 4, 5])
        assert uc.vacation_until is None


class TestWasOnVacation:
    """Test the _was_on_vacation helper directly."""

    def test_no_vacation(self, make_uc):
        uc = make_uc(vacation_until=None)
        assert not _was_on_vacation(uc, date(2026, 3, 30), date(2026, 4, 2))

    def test_vacation_covers(self, make_uc):
        uc = make_uc(vacation_until=date(2026, 4, 1))
        assert _was_on_vacation(uc, date(2026, 3, 30), date(2026, 4, 2))

    def test_vacation_too_early(self, make_uc):
        """Vacation ended before the gap started."""
        uc = make_uc(vacation_until=date(2026, 3, 29))
        assert not _was_on_vacation(uc, date(2026, 3, 30), date(2026, 4, 2))

    def test_report_too_late_after_vacation(self, make_uc):
        """Report comes more than 1 day after vacation ends."""
        uc = make_uc(vacation_until=date(2026, 3, 31))
        assert not _was_on_vacation(uc, date(2026, 3, 30), date(2026, 4, 3))
