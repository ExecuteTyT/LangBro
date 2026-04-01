"""Aggregate stats helpers for leaderboard / digest queries."""

from datetime import date

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import DailyReport, ReportActivity, UserChallenge


class StatsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_leaderboard(
        self, challenge_id: int, *, limit: int = 20
    ) -> list[UserChallenge]:
        stmt = (
            select(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                UserChallenge.status == "active",
            )
            .order_by(UserChallenge.total_points.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_week_points(
        self, challenge_id: int, week_start: date, week_end: date
    ) -> list[tuple[int, int]]:
        """Return list of (user_challenge_id, week_points) sorted desc."""
        stmt = (
            select(
                DailyReport.user_challenge_id,
                func.sum(DailyReport.total_points).label("pts"),
            )
            .join(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                DailyReport.report_date >= week_start,
                DailyReport.report_date <= week_end,
            )
            .group_by(DailyReport.user_challenge_id)
            .order_by(func.sum(DailyReport.total_points).desc())
        )
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_day_aggregate(
        self, challenge_id: int, report_date: date
    ) -> dict:
        """Get aggregate stats for a challenge on a date for digest."""
        stmt = (
            select(
                func.count(DailyReport.id).label("report_count"),
                func.sum(DailyReport.total_points).label("total_pts"),
            )
            .join(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                DailyReport.report_date == report_date,
            )
        )
        result = await self.session.execute(stmt)
        row = result.one()

        # Activity breakdown
        act_stmt = (
            select(
                ReportActivity.category,
                func.sum(ReportActivity.duration_minutes).label("total_min"),
                func.sum(ReportActivity.count).label("total_count"),
            )
            .join(DailyReport)
            .join(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                DailyReport.report_date == report_date,
            )
            .group_by(ReportActivity.category)
        )
        act_result = await self.session.execute(act_stmt)
        activities = {
            r.category: {"minutes": r.total_min or 0, "count": r.total_count or 0}
            for r in act_result.all()
        }

        return {
            "report_count": row.report_count or 0,
            "total_points": row.total_pts or 0,
            "activities": activities,
        }
