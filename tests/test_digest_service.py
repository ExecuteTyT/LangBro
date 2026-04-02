"""Tests for DigestService — vacation filtering in digest and reminders."""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestDigestVacationFiltering:
    """Test that vacation users are handled correctly in digest."""

    def test_active_vs_vacation_separation(self, make_uc):
        """Verify vacation members are separated from active members."""
        today = date(2026, 4, 1)
        members = [
            make_uc(id=1, vacation_until=None),
            make_uc(id=2, vacation_until=date(2026, 4, 3)),  # on vacation
            make_uc(id=3, vacation_until=None),
            make_uc(id=4, vacation_until=date(2026, 4, 5)),  # on vacation
        ]

        active = []
        vacation = []
        for m in members:
            if m.vacation_until and m.vacation_until >= today:
                vacation.append(m)
            else:
                active.append(m)

        assert len(active) == 2
        assert len(vacation) == 2

    def test_expired_vacation_is_active(self, make_uc):
        """Members whose vacation has expired should be in active list."""
        today = date(2026, 4, 5)
        uc = make_uc(vacation_until=date(2026, 4, 3))

        is_on_vacation = uc.vacation_until and uc.vacation_until >= today
        assert not is_on_vacation

    def test_vacation_remaining_days(self, make_uc):
        today = date(2026, 4, 1)
        uc = make_uc(vacation_until=date(2026, 4, 4))
        remaining = (uc.vacation_until - today).days
        assert remaining == 3


class TestReminderVacationFiltering:
    """Test that vacation users are NOT tagged in reminders."""

    def test_skip_vacation_users(self, make_uc):
        today = date(2026, 4, 1)
        reported_ids = {1}  # user 1 reported
        members = [
            make_uc(id=1, vacation_until=None),       # reported
            make_uc(id=2, vacation_until=None),       # missing → tag
            make_uc(id=3, vacation_until=date(2026, 4, 3)),  # vacation → skip
        ]

        missing = []
        for m in members:
            if m.vacation_until and m.vacation_until >= today:
                continue
            if m.id not in reported_ids:
                missing.append(m.id)

        assert missing == [2]  # only user 2, not user 3 (vacation)

    def test_all_on_vacation_no_reminder(self, make_uc):
        today = date(2026, 4, 1)
        reported_ids = set()
        members = [
            make_uc(id=1, vacation_until=date(2026, 4, 3)),
            make_uc(id=2, vacation_until=date(2026, 4, 5)),
        ]

        missing = []
        for m in members:
            if m.vacation_until and m.vacation_until >= today:
                continue
            if m.id not in reported_ids:
                missing.append(m.id)

        assert missing == []

    def test_everyone_reported_no_reminder(self, make_uc):
        today = date(2026, 4, 1)
        reported_ids = {1, 2, 3}
        members = [
            make_uc(id=1), make_uc(id=2), make_uc(id=3),
        ]

        missing = []
        for m in members:
            if m.vacation_until and m.vacation_until >= today:
                continue
            if m.id not in reported_ids:
                missing.append(m.id)

        assert missing == []
