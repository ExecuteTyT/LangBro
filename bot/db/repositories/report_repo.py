from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import DailyReport, ReportActivity, UserChallenge


class ReportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_today_report(
        self, user_challenge_id: int, report_date: date
    ) -> DailyReport | None:
        stmt = select(DailyReport).where(
            DailyReport.user_challenge_id == user_challenge_id,
            DailyReport.report_date == report_date,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_report(self, report: DailyReport) -> DailyReport:
        self.session.add(report)
        await self.session.flush()
        return report

    async def delete_activities(self, report_id: int) -> None:
        stmt = select(ReportActivity).where(
            ReportActivity.report_id == report_id
        )
        result = await self.session.execute(stmt)
        for activity in result.scalars().all():
            await self.session.delete(activity)
        await self.session.flush()

    async def save_activities(
        self, activities: list[ReportActivity]
    ) -> None:
        for a in activities:
            self.session.add(a)
        await self.session.flush()

    async def get_user_rank(
        self, challenge_id: int, user_challenge_id: int
    ) -> tuple[int, int]:
        """Return (rank, total_members) for a user in a challenge."""
        stmt = (
            select(UserChallenge.id, UserChallenge.total_points)
            .where(
                UserChallenge.challenge_id == challenge_id,
                UserChallenge.status == "active",
            )
            .order_by(UserChallenge.total_points.desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        rank = 1
        total = len(rows)
        for i, row in enumerate(rows, 1):
            if row.id == user_challenge_id:
                rank = i
                break

        return rank, total

    async def get_today_reported_ids(
        self, challenge_id: int, report_date: date
    ) -> set[int]:
        """Return set of user_challenge_ids that reported today."""
        stmt = (
            select(DailyReport.user_challenge_id)
            .join(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                DailyReport.report_date == report_date,
            )
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())

    async def get_reports_for_date(
        self, challenge_id: int, report_date: date
    ) -> list[DailyReport]:
        """Get all reports for a challenge on a given date."""
        stmt = (
            select(DailyReport)
            .join(UserChallenge)
            .where(
                UserChallenge.challenge_id == challenge_id,
                DailyReport.report_date == report_date,
            )
            .order_by(DailyReport.total_points.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
