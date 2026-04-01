from bot.db.models import Challenge
from bot.llm.schemas import ParsedActivity

# Default multipliers matching the Challenge model defaults
DEFAULT_MULTIPLIERS = {
    "speaking": 2,
    "listening": 1,
    "reading": 1.5,
    "writing": 2,
    "vocabulary": 3,
    "grammar": 5,
    "app_practice": 10,
    "other": 5,
    "wotd_bonus": 20,
    "quiz_correct": 15,
    "quiz_speed_bonus": 10,
}


def calculate_activity_points(
    activity: ParsedActivity,
    multipliers: dict | None = None,
) -> int:
    """Calculate points for a single activity."""
    m = multipliers or DEFAULT_MULTIPLIERS
    mult = m.get(activity.category, 5)

    if activity.duration_minutes:
        return int(activity.duration_minutes * mult)
    elif activity.count:
        return int(activity.count * mult)
    else:
        # Single activity without duration/count
        return int(mult)


def calculate_report_points(
    activities: list[ParsedActivity],
    multipliers: dict | None = None,
) -> tuple[int, list[int]]:
    """Calculate total points and per-activity points.

    Returns:
        (total_points, list of per-activity points)
    """
    per_activity = [calculate_activity_points(a, multipliers) for a in activities]
    return sum(per_activity), per_activity
