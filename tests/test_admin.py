"""Tests for admin handler — keyboard builders and helper logic."""

import pytest
from datetime import time

from bot.handlers.admin import (
    _settings_main_kb,
    _schedule_kb,
    _features_kb,
    _times_kb,
    FEATURE_LABELS,
    WEEKDAY_NAMES,
)


class TestSettingsMainKb:
    """Test main settings keyboard builder."""

    def test_active_challenge(self, make_challenge):
        ch = make_challenge(status="active")
        kb = _settings_main_kb(ch)
        buttons = kb.inline_keyboard
        assert len(buttons) == 5  # schedule, times, features, status, close
        # Status button shows active
        status_btn = buttons[3][0]
        assert "active" in status_btn.text
        assert "✅" in status_btn.text

    def test_paused_challenge(self, make_challenge):
        ch = make_challenge(status="paused")
        kb = _settings_main_kb(ch)
        status_btn = kb.inline_keyboard[3][0]
        assert "paused" in status_btn.text
        assert "⏸" in status_btn.text

    def test_close_button_present(self, make_challenge):
        ch = make_challenge()
        kb = _settings_main_kb(ch)
        close_btn = kb.inline_keyboard[-1][0]
        assert close_btn.callback_data == "settings:close"


class TestScheduleKb:
    """Test schedule days toggle keyboard."""

    def test_weekdays_selected(self):
        kb = _schedule_kb([1, 2, 3, 4, 5])
        # Flatten all buttons except last two rows (presets + back)
        day_buttons = []
        for row in kb.inline_keyboard[:-2]:
            day_buttons.extend(row)

        # Mon-Fri should have ✅, Sat-Sun should have ⬜
        for btn in day_buttons:
            day_num = int(btn.callback_data.split(":")[1])
            if day_num <= 5:
                assert "✅" in btn.text
            else:
                assert "⬜" in btn.text

    def test_all_days_selected(self):
        kb = _schedule_kb([1, 2, 3, 4, 5, 6, 7])
        day_buttons = []
        for row in kb.inline_keyboard[:-2]:
            day_buttons.extend(row)
        for btn in day_buttons:
            assert "✅" in btn.text

    def test_no_days_empty_list(self):
        kb = _schedule_kb([])
        day_buttons = []
        for row in kb.inline_keyboard[:-2]:
            day_buttons.extend(row)
        for btn in day_buttons:
            assert "⬜" in btn.text

    def test_presets_row(self):
        kb = _schedule_kb([1, 2, 3, 4, 5])
        presets = kb.inline_keyboard[-2]
        assert len(presets) == 2
        assert presets[0].callback_data == "sched_preset:weekdays"
        assert presets[1].callback_data == "sched_preset:daily"

    def test_back_button(self):
        kb = _schedule_kb([1])
        back = kb.inline_keyboard[-1][0]
        assert back.callback_data == "settings:main"


class TestFeaturesKb:
    """Test features toggle keyboard."""

    def test_all_enabled(self):
        features = {k: True for k in FEATURE_LABELS}
        kb = _features_kb(features)
        for row in kb.inline_keyboard[:-1]:  # exclude back button
            assert "✅" in row[0].text

    def test_all_disabled(self):
        features = {k: False for k in FEATURE_LABELS}
        kb = _features_kb(features)
        for row in kb.inline_keyboard[:-1]:
            assert "❌" in row[0].text

    def test_mixed_features(self):
        features = {
            "daily_digest": True,
            "reminders": False,
            "word_of_day": True,
            "pop_quiz": False,
            "weekly_battles": True,
            "weekly_digest": False,
        }
        kb = _features_kb(features)
        buttons = [row[0] for row in kb.inline_keyboard[:-1]]
        enabled_count = sum(1 for b in buttons if "✅" in b.text)
        disabled_count = sum(1 for b in buttons if "❌" in b.text)
        assert enabled_count == 3
        assert disabled_count == 3

    def test_callback_data_format(self):
        kb = _features_kb({})
        for row in kb.inline_keyboard[:-1]:
            btn = row[0]
            assert btn.callback_data.startswith("feat_toggle:")

    def test_six_feature_buttons(self):
        kb = _features_kb({})
        feature_buttons = kb.inline_keyboard[:-1]
        assert len(feature_buttons) == 6

    def test_back_button(self):
        kb = _features_kb({})
        back = kb.inline_keyboard[-1][0]
        assert back.callback_data == "settings:main"


class TestTimesKb:
    """Test times settings keyboard."""

    def test_shows_current_times(self, make_challenge):
        ch = make_challenge(
            digest_time=time(22, 0),
            reminder_time=time(20, 0),
            wotd_time=time(8, 0),
            report_deadline_time=time(23, 59),
        )
        kb = _times_kb(ch)
        texts = [row[0].text for row in kb.inline_keyboard[:-1]]
        assert any("22:00" in t for t in texts)
        assert any("20:00" in t for t in texts)
        assert any("08:00" in t for t in texts)
        assert any("23:59" in t for t in texts)

    def test_four_time_settings(self, make_challenge):
        ch = make_challenge()
        kb = _times_kb(ch)
        time_buttons = kb.inline_keyboard[:-1]
        assert len(time_buttons) == 4

    def test_callback_data_format(self, make_challenge):
        ch = make_challenge()
        kb = _times_kb(ch)
        for row in kb.inline_keyboard[:-1]:
            assert row[0].callback_data.startswith("time_edit:")


class TestWeekdayNames:
    """Test weekday constants."""

    def test_seven_days(self):
        assert len(WEEKDAY_NAMES) == 7

    def test_monday_is_1(self):
        assert WEEKDAY_NAMES[1] == "Пн"

    def test_sunday_is_7(self):
        assert WEEKDAY_NAMES[7] == "Вс"
