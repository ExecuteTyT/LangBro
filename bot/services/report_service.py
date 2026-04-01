import logging
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Challenge,
    DailyReport,
    ReportActivity,
    User,
    UserChallenge,
)
from bot.db.repositories.report_repo import ReportRepository
from bot.llm.client import GeminiClient
from bot.llm.prompts.bot_persona import BASE_SYSTEM_PROMPT
from bot.llm.prompts.report_parser import (
    REPORT_PARSE_SYSTEM,
    REPORT_PARSE_USER,
    REPORT_RESPONSE_USER,
)
from bot.llm.schemas import ReportParseResult
from bot.services.scoring_service import calculate_report_points
from bot.services.streak_service import update_streak

logger = logging.getLogger(__name__)

ACTIVITY_ICONS = {
    "speaking": "🗣",
    "listening": "👂",
    "reading": "📖",
    "writing": "✍️",
    "vocabulary": "📚",
    "grammar": "📝",
    "app_practice": "📱",
    "other": "🔹",
}


class ReportService:
    def __init__(self, session: AsyncSession, gemini: GeminiClient):
        self.session = session
        self.repo = ReportRepository(session)
        self.gemini = gemini

    async def process_report(
        self,
        *,
        raw_text: str,
        user: User,
        uc: UserChallenge,
        challenge: Challenge,
        message_id: int | None = None,
        source: str = "group",
    ) -> str:
        """Parse report via LLM, save, update streak, return formatted response."""
        today = datetime.now(timezone.utc).date()
        name = user.display_name or user.first_name

        # 1. Parse report via LLM
        prompt = REPORT_PARSE_USER.format(
            display_name=name,
            english_level=user.english_level,
            raw_text=raw_text,
            word_of_the_day="нет",  # TODO: look up today's WotD
        )
        parsed_data = await self.gemini.call_json(
            prompt=prompt,
            system=REPORT_PARSE_SYSTEM,
            feature="report_parse",
            temperature=0.1,
            max_tokens=1000,
        )
        parsed = ReportParseResult.model_validate(parsed_data)

        # 2. Calculate points
        multipliers = challenge.scoring_multipliers or None
        total_points, per_activity_pts = calculate_report_points(
            parsed.activities, multipliers
        )

        # 3. Check for existing report (overwrite)
        is_rewrite = False
        existing = await self.repo.get_today_report(uc.id, today)
        if existing:
            is_rewrite = True
            # Revert old points from user_challenge
            uc.total_points -= existing.total_points
            uc.total_reports -= 1
            await self.repo.delete_activities(existing.id)
            report = existing
            report.raw_text = raw_text
            report.parsed_data = parsed_data
            report.total_points = total_points
            report.summary = parsed.raw_summary
            report.message_id = message_id
            report.source = source
            report.wotd_used = parsed.word_of_day_used
        else:
            report = DailyReport(
                user_challenge_id=uc.id,
                report_date=today,
                raw_text=raw_text,
                message_id=message_id,
                source=source,
                parsed_data=parsed_data,
                total_points=total_points,
                summary=parsed.raw_summary,
                wotd_used=parsed.word_of_day_used,
                llm_model="gemini-2.5-flash",
            )
            await self.repo.save_report(report)

        # 4. Save activities
        activities = []
        for act, pts in zip(parsed.activities, per_activity_pts):
            activities.append(
                ReportActivity(
                    report_id=report.id,
                    category=act.category,
                    description=act.description,
                    duration_minutes=act.duration_minutes,
                    count=act.count,
                    points=pts,
                    details=act.details,
                )
            )
        await self.repo.save_activities(activities)

        # 5. Update streak and stats
        schedule_days = challenge.schedule_days or [1, 2, 3, 4, 5]
        update_streak(uc, today, schedule_days)
        uc.total_points += total_points
        uc.total_reports += 1
        await self.session.flush()

        # 6. Get rank
        rank, total_members = await self.repo.get_user_rank(challenge.id, uc.id)

        # 7. Build activity summary for LLM response
        act_lines = []
        for act, pts in zip(parsed.activities, per_activity_pts):
            icon = ACTIVITY_ICONS.get(act.category, "🔹")
            label = act.category.replace("_", " ").title()
            detail = ""
            if act.duration_minutes:
                detail = f"{act.duration_minutes} мин"
            elif act.count:
                detail = f"{act.count} шт"
            desc = f": {act.description}" if act.description else ""
            act_lines.append(f"{icon} {label}{desc} {detail} (+{pts} pts)")

        act_text = "\n".join(act_lines)
        activities_summary = ", ".join(
            f"{a.category} {a.duration_minutes or a.count or 1}"
            for a in parsed.activities
        )

        # 8. Generate motivational comment
        try:
            response_prompt = REPORT_RESPONSE_USER.format(
                display_name=name,
                english_level=user.english_level,
                parsed_activities_summary=activities_summary,
                total_points=total_points,
                current_streak=uc.current_streak,
                best_streak=uc.best_streak,
                rank=rank,
                total_members=total_members,
            )
            motivation = await self.gemini.call(
                prompt=response_prompt,
                system=BASE_SYSTEM_PROMPT,
                feature="report_response",
                temperature=0.8,
                max_tokens=300,
            )
        except Exception:
            motivation = "Keep going! 💪"

        # 9. Format final response
        header = "✅ Отчёт принят" if not is_rewrite else "✅ Отчёт обновлён"
        response = (
            f"{header}, <b>{name}</b>!\n\n"
            f"{act_text}\n\n"
            f"💰 Итого за день: <b>{total_points} pts</b>\n"
            f"🔥 Streak: <b>{uc.current_streak}</b> дней\n"
            f"📊 Позиция: #{rank} из {total_members}\n\n"
            f"{motivation}"
        )
        return response
