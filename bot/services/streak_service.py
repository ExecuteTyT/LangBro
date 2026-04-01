from datetime import date, timedelta

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


def _was_on_vacation(
    uc: UserChallenge,
    last_report: date,
    report_date: date,
) -> bool:
    """Check if the gap between last_report and report_date is covered by vacation.

    vacation_until marks the end of vacation. If the entire gap falls within
    the vacation window, streak should not be broken.
    """
    if not uc.vacation_until:
        return False
    # Vacation was active if vacation_until >= last_report (vacation started
    # before or on the last report day and extends to cover the gap).
    # The gap is covered if report_date is <= vacation_until + 1 day
    # (user returns the day after vacation ends or on the end day itself).
    return uc.vacation_until >= last_report and report_date <= uc.vacation_until + timedelta(days=1)


def update_streak(
    uc: UserChallenge,
    report_date: date,
    schedule_days: list[int],
) -> None:
    """Update streak on the UserChallenge object (O(1), no history scan).

    Respects vacation: streak is not broken if the gap is covered by
    an active vacation period (vacation_until).
    """
    last = uc.last_report_date

    if last is None:
        uc.current_streak = 1
    elif last == report_date:
        # Same day re-report — streak unchanged
        pass
    elif is_next_scheduled_day(last, report_date, schedule_days):
        uc.current_streak += 1
    elif _was_on_vacation(uc, last, report_date):
        # Gap covered by vacation — streak continues
        uc.current_streak += 1
    else:
        # Gap → reset
        uc.current_streak = 1

    uc.best_streak = max(uc.best_streak, uc.current_streak)
    uc.last_report_date = report_date

    # Clear vacation if it has ended
    if uc.vacation_until and report_date > uc.vacation_until:
        uc.vacation_until = None
