import logging
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, UserChallenge
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.db.repositories.report_repo import ReportRepository
from bot.db.repositories.stats_repo import StatsRepository
from bot.llm.client import GeminiClient
from bot.llm.prompts.bot_persona import BASE_SYSTEM_PROMPT
from bot.llm.prompts.digest_generator import (
    FUN_FACT_SYSTEM,
    FUN_FACT_USER,
    REMINDER_USER,
)

logger = logging.getLogger(__name__)

WEEKDAYS_RU = {
    1: "понедельник",
    2: "вторник",
    3: "среда",
    4: "четверг",
    5: "пятница",
    6: "суббота",
    7: "воскресенье",
}

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}


class DigestService:
    def __init__(self, session: AsyncSession, gemini: GeminiClient):
        self.session = session
        self.gemini = gemini

    async def generate_daily_digest(self, challenge: Challenge) -> str | None:
        """Generate the daily digest text for a challenge."""
        today = datetime.now(timezone.utc).date()
        report_repo = ReportRepository(self.session)
        stats_repo = StatsRepository(self.session)
        challenge_repo = ChallengeRepository(self.session)

        members = await challenge_repo.get_challenge_members(challenge.id)
        if not members:
            return None

        # Separate vacation members
        active_members = []
        vacation_members = []
        for m in members:
            if m.vacation_until and m.vacation_until >= today:
                vacation_members.append(m)
            else:
                active_members.append(m)

        total_members = len(members)
        reports = await report_repo.get_reports_for_date(challenge.id, today)
        reported_ids = {r.user_challenge_id for r in reports}

        # Day aggregate
        agg = await stats_repo.get_day_aggregate(challenge.id, today)
        activities = agg.get("activities", {})
        total_minutes = sum(a.get("minutes", 0) for a in activities.values())
        total_words = activities.get("vocabulary", {}).get("count", 0)
        speaking_min = activities.get("speaking", {}).get("minutes", 0)

        # Date formatting
        weekday = WEEKDAYS_RU.get(today.isoweekday(), "")
        date_str = f"{today.day} {MONTHS_RU.get(today.month, '')}, {weekday}"

        # Top 3
        top3_lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, report in enumerate(reports[:3]):
            await self.session.refresh(report, ["user_challenge"])
            uc = report.user_challenge
            await self.session.refresh(uc, ["user"])
            name = uc.user.display_name or uc.user.first_name
            summary = report.summary or ""
            top3_lines.append(
                f"{medals[i]} <b>{name}</b> — {report.total_points} pts ({summary})"
            )

        # Streak leaders
        streak_leaders = sorted(members, key=lambda m: m.current_streak, reverse=True)[:3]
        streak_parts = []
        for m in streak_leaders:
            if m.current_streak > 0:
                await self.session.refresh(m, ["user"])
                name = m.user.display_name or m.user.first_name
                streak_parts.append(f"{name}: {m.current_streak} дней")

        # Missing members (exclude vacation)
        missing = []
        for m in active_members:
            if m.id not in reported_ids:
                await self.session.refresh(m, ["user"])
                u = m.user
                if u.username:
                    missing.append(f"@{u.username}")
                else:
                    missing.append(u.display_name or u.first_name)

        # Vacation members
        vacation_names = []
        for m in vacation_members:
            await self.session.refresh(m, ["user"])
            name = m.user.display_name or m.user.first_name
            remaining = (m.vacation_until - today).days
            vacation_names.append(f"{name} ({remaining} дн.)")

        # Fun fact from LLM
        fun_fact = ""
        try:
            fun_fact_prompt = FUN_FACT_USER.format(
                total_minutes=total_minutes,
                total_words=total_words,
                total_speaking_minutes=speaking_min,
                reported_count=len(reported_ids),
                total_count=total_members,
            )
            fun_fact = await self.gemini.call(
                prompt=fun_fact_prompt,
                system=FUN_FACT_SYSTEM,
                feature="digest_fun_fact",
                temperature=0.8,
                max_tokens=200,
            )
        except Exception as e:
            logger.warning("Failed to generate fun fact: %s", e)

        # Build digest
        parts = [f"📊 <b>Daily Digest — {date_str}</b>\n"]
        parts.append(f"👥 Отчитались: <b>{len(reported_ids)}/{total_members}</b>\n")

        if top3_lines:
            parts.append("🏆 <b>Top-3 дня:</b>")
            parts.extend(top3_lines)
            parts.append("")

        if streak_parts:
            parts.append(f"🔥 Streak-лидеры: {' | '.join(streak_parts)}\n")

        if missing:
            parts.append(f"😴 Не отчитались: {', '.join(missing)}\n")

        if vacation_names:
            parts.append(f"🏖 На каникулах: {', '.join(vacation_names)}\n")

        # Group stats
        hours = total_minutes // 60
        mins = total_minutes % 60
        time_str = f"{hours}ч {mins}мин" if hours else f"{mins} мин"
        parts.append(
            f"📈 Группа за сегодня: ⏱ {time_str} практики"
            + (f", 📚 {total_words} новых слов" if total_words else "")
            + (f", 🗣 {speaking_min} мин speaking" if speaking_min else "")
        )

        if fun_fact:
            parts.append(f"\n💬 {fun_fact}")

        return "\n".join(parts)

    async def generate_reminder(self, challenge: Challenge) -> str | None:
        """Generate a reminder message tagging users who haven't reported."""
        today = datetime.now(timezone.utc).date()
        challenge_repo = ChallengeRepository(self.session)
        report_repo = ReportRepository(self.session)

        members = await challenge_repo.get_challenge_members(challenge.id)
        reported_ids = await report_repo.get_today_reported_ids(challenge.id, today)

        missing = []
        for m in members:
            # Skip vacation users — don't tag them
            if m.vacation_until and m.vacation_until >= today:
                continue
            if m.id not in reported_ids:
                await self.session.refresh(m, ["user"])
                u = m.user
                if u.username:
                    missing.append(f"@{u.username}")
                else:
                    missing.append(u.display_name or u.first_name)

        if not missing:
            return None  # Everyone reported

        weekday = WEEKDAYS_RU.get(today.isoweekday(), "")

        try:
            prompt = REMINDER_USER.format(
                time=challenge.reminder_time.strftime("%H:%M"),
                deadline=challenge.report_deadline_time.strftime("%H:%M"),
                missing_names=", ".join(missing),
                weekday=weekday,
                day_number="—",
            )
            text = await self.gemini.call(
                prompt=prompt,
                system=BASE_SYSTEM_PROMPT,
                feature="reminder",
                temperature=0.8,
                max_tokens=200,
            )
            return text
        except Exception as e:
            logger.warning("Failed to generate reminder: %s", e)
            # Fallback static reminder
            return (
                f"⏰ Напоминание! Сегодня ещё не отчитались:\n"
                f"{', '.join(missing)}\n\n"
                f"Дедлайн — {challenge.report_deadline_time.strftime('%H:%M')}. Don't miss it! 💪"
            )
