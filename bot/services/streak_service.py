from datetime import date

from bot.db.models import UserChallenge


def is_next_scheduled_day(
    last_date: date,
    report_date: date,
    schedule_days: list[int],
) -> bool:
    """Check if report_date is the next scheduled day after last_date.

    schedule_days: list of ISO weekday numbers (1=Mon, 7=Sun).
    """
    if not schedule_days:
        # No schedule → every day counts
        return (report_date - last_date).days == 1

    current = last_date
    for _ in range(7):  # max gap is 7 days
        current = date.fromordinal(current.toordinal() + 1)
        if current.isoweekday() in schedule_days:
            return current == report_date
    return False


def update_streak(
    uc: UserChallenge,
    report_date: date,
    schedule_days: list[int],
) -> None:
    """Update streak on the UserChallenge object (O(1), no history scan)."""
    last = uc.last_report_date

    if last is None:
        uc.current_streak = 1
    elif last == report_date:
        # Same day re-report — streak unchanged
        pass
    elif is_next_scheduled_day(last, report_date, schedule_days):
        uc.current_streak += 1
    else:
        # Gap → reset
        uc.current_streak = 1

    uc.best_streak = max(uc.best_streak, uc.current_streak)
    uc.last_report_date = report_date
