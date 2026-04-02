"""LangBro Admin Panel — FastAPI application."""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Query
from sqlalchemy import func, select, text

from admin.auth import require_auth
from admin.database import async_session_factory, engine

# Import bot models (shared schema)
import sys
import os

# Ensure bot package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.db.models import (
    Base,
    BattlePair,
    Challenge,
    ConversationHistory,
    DailyReport,
    LLMUsageLog,
    Quiz,
    QuizAnswer,
    ReportActivity,
    User,
    UserChallenge,
    WeeklyBattle,
    WordOfTheDay,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Admin panel starting")
    yield
    await engine.dispose()
    logger.info("Admin panel stopped")


app = FastAPI(
    title="LangBro Admin Panel",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — no auth required."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}


# ─── Dashboard ──────────────────────────────────────────────────────────────

@app.get("/api/dashboard", dependencies=[Depends(require_auth)])
async def dashboard():
    """Overview: key metrics for the service."""
    async with async_session_factory() as session:
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Users
        total_users = (await session.execute(
            select(func.count(User.id))
        )).scalar() or 0

        # Challenges
        challenges_by_status = dict(
            (await session.execute(
                select(Challenge.status, func.count(Challenge.id))
                .group_by(Challenge.status)
            )).all()
        )

        # Reports today
        reports_today = (await session.execute(
            select(func.count(DailyReport.id))
            .where(DailyReport.report_date == today)
        )).scalar() or 0

        # Reports this week
        reports_week = (await session.execute(
            select(func.count(DailyReport.id))
            .where(DailyReport.report_date >= week_ago)
        )).scalar() or 0

        # Active participants (reported in last 7 days)
        active_participants = (await session.execute(
            select(func.count(func.distinct(DailyReport.user_challenge_id)))
            .where(DailyReport.report_date >= week_ago)
        )).scalar() or 0

        # LLM stats (last 24h)
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        llm_24h = (await session.execute(
            select(
                func.count(LLMUsageLog.id).label("calls"),
                func.sum(LLMUsageLog.input_tokens).label("input_tokens"),
                func.sum(LLMUsageLog.output_tokens).label("output_tokens"),
                func.avg(LLMUsageLog.latency_ms).label("avg_latency_ms"),
                func.count(LLMUsageLog.error).label("errors"),
            ).where(LLMUsageLog.created_at >= day_ago)
        )).first()

        llm_errors_24h = (await session.execute(
            select(func.count(LLMUsageLog.id))
            .where(LLMUsageLog.created_at >= day_ago)
            .where(LLMUsageLog.error.isnot(None))
        )).scalar() or 0

        return {
            "users": {"total": total_users},
            "challenges": challenges_by_status,
            "reports": {
                "today": reports_today,
                "this_week": reports_week,
                "active_participants_7d": active_participants,
            },
            "llm_24h": {
                "calls": llm_24h.calls if llm_24h else 0,
                "input_tokens": llm_24h.input_tokens if llm_24h else 0,
                "output_tokens": llm_24h.output_tokens if llm_24h else 0,
                "avg_latency_ms": round(llm_24h.avg_latency_ms, 1) if llm_24h and llm_24h.avg_latency_ms else 0,
                "errors": llm_errors_24h,
            },
        }


# ─── Challenges ─────────────────────────────────────────────────────────────

@app.get("/api/challenges", dependencies=[Depends(require_auth)])
async def list_challenges():
    """List all challenges with member counts."""
    async with async_session_factory() as session:
        stmt = (
            select(
                Challenge,
                func.count(UserChallenge.id).label("member_count"),
            )
            .outerjoin(UserChallenge, (UserChallenge.challenge_id == Challenge.id) & (UserChallenge.status == "active"))
            .group_by(Challenge.id)
            .order_by(Challenge.created_at.desc())
        )
        rows = (await session.execute(stmt)).all()

        return [
            {
                "id": ch.id,
                "title": ch.title,
                "invite_code": ch.invite_code,
                "status": ch.status,
                "chat_id": ch.chat_id,
                "member_count": count,
                "timezone": ch.timezone,
                "schedule_days": ch.schedule_days,
                "features_enabled": ch.features_enabled,
                "created_at": ch.created_at.isoformat() if ch.created_at else None,
            }
            for ch, count in rows
        ]


@app.get("/api/challenges/{challenge_id}", dependencies=[Depends(require_auth)])
async def get_challenge(challenge_id: int):
    """Challenge details with members and recent reports."""
    async with async_session_factory() as session:
        ch = await session.get(Challenge, challenge_id)
        if not ch:
            return {"error": "Challenge not found"}

        # Members
        members_stmt = (
            select(UserChallenge, User)
            .join(User, User.id == UserChallenge.user_id)
            .where(UserChallenge.challenge_id == challenge_id)
            .order_by(UserChallenge.total_points.desc())
        )
        members_rows = (await session.execute(members_stmt)).all()

        members = []
        for uc, user in members_rows:
            members.append({
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "display_name": user.display_name,
                "status": uc.status,
                "total_points": uc.total_points,
                "total_reports": uc.total_reports,
                "current_streak": uc.current_streak,
                "best_streak": uc.best_streak,
                "vacation_until": uc.vacation_until.isoformat() if uc.vacation_until else None,
            })

        # Recent reports (last 7 days)
        week_ago = date.today() - timedelta(days=7)
        reports_stmt = (
            select(func.count(DailyReport.id), DailyReport.report_date)
            .join(UserChallenge, UserChallenge.id == DailyReport.user_challenge_id)
            .where(UserChallenge.challenge_id == challenge_id)
            .where(DailyReport.report_date >= week_ago)
            .group_by(DailyReport.report_date)
            .order_by(DailyReport.report_date)
        )
        report_rows = (await session.execute(reports_stmt)).all()

        return {
            "id": ch.id,
            "title": ch.title,
            "invite_code": ch.invite_code,
            "status": ch.status,
            "chat_id": ch.chat_id,
            "timezone": ch.timezone,
            "schedule_days": ch.schedule_days,
            "features_enabled": ch.features_enabled,
            "scoring_multipliers": ch.scoring_multipliers,
            "created_at": ch.created_at.isoformat() if ch.created_at else None,
            "members": members,
            "reports_by_date": [
                {"date": d.isoformat(), "count": c} for c, d in report_rows
            ],
        }


# ─── Users ──────────────────────────────────────────────────────────────────

@app.get("/api/users", dependencies=[Depends(require_auth)])
async def list_users(
    search: str = Query(default="", description="Search by username or first_name"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List users with optional search."""
    async with async_session_factory() as session:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                User.username.ilike(pattern) | User.first_name.ilike(pattern)
            )
        users = (await session.execute(stmt)).scalars().all()

        total = (await session.execute(
            select(func.count(User.id))
        )).scalar() or 0

        return {
            "total": total,
            "users": [
                {
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "display_name": u.display_name,
                    "english_level": u.english_level,
                    "onboarding_complete": u.onboarding_complete,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ],
        }


@app.get("/api/users/{user_id}", dependencies=[Depends(require_auth)])
async def get_user(user_id: int):
    """User details with challenge memberships."""
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if not user:
            return {"error": "User not found"}

        # Challenge memberships
        stmt = (
            select(UserChallenge, Challenge)
            .join(Challenge, Challenge.id == UserChallenge.challenge_id)
            .where(UserChallenge.user_id == user_id)
        )
        memberships = (await session.execute(stmt)).all()

        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "display_name": user.display_name,
            "english_level": user.english_level,
            "learning_goal": user.learning_goal,
            "onboarding_complete": user.onboarding_complete,
            "active_challenge_id": user.active_challenge_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "challenges": [
                {
                    "challenge_id": ch.id,
                    "title": ch.title,
                    "status": uc.status,
                    "total_points": uc.total_points,
                    "total_reports": uc.total_reports,
                    "current_streak": uc.current_streak,
                    "best_streak": uc.best_streak,
                }
                for uc, ch in memberships
            ],
        }


# ─── LLM Usage ──────────────────────────────────────────────────────────────

@app.get("/api/llm/stats", dependencies=[Depends(require_auth)])
async def llm_stats(
    days: int = Query(default=7, ge=1, le=90),
):
    """LLM usage statistics grouped by feature and day."""
    async with async_session_factory() as session:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # By feature
        by_feature = (await session.execute(
            select(
                LLMUsageLog.feature,
                func.count(LLMUsageLog.id).label("calls"),
                func.sum(LLMUsageLog.input_tokens).label("input_tokens"),
                func.sum(LLMUsageLog.output_tokens).label("output_tokens"),
                func.avg(LLMUsageLog.latency_ms).label("avg_latency_ms"),
            )
            .where(LLMUsageLog.created_at >= since)
            .group_by(LLMUsageLog.feature)
            .order_by(func.count(LLMUsageLog.id).desc())
        )).all()

        # By day
        by_day = (await session.execute(
            select(
                func.date_trunc("day", LLMUsageLog.created_at).label("day"),
                func.count(LLMUsageLog.id).label("calls"),
                func.sum(LLMUsageLog.input_tokens).label("input_tokens"),
                func.sum(LLMUsageLog.output_tokens).label("output_tokens"),
            )
            .where(LLMUsageLog.created_at >= since)
            .group_by(text("1"))
            .order_by(text("1"))
        )).all()

        # Errors
        errors = (await session.execute(
            select(
                LLMUsageLog.feature,
                func.count(LLMUsageLog.id).label("error_count"),
            )
            .where(LLMUsageLog.created_at >= since)
            .where(LLMUsageLog.error.isnot(None))
            .group_by(LLMUsageLog.feature)
        )).all()

        # Recent errors (last 20)
        recent_errors = (await session.execute(
            select(LLMUsageLog)
            .where(LLMUsageLog.error.isnot(None))
            .order_by(LLMUsageLog.created_at.desc())
            .limit(20)
        )).scalars().all()

        return {
            "period_days": days,
            "by_feature": [
                {
                    "feature": row.feature,
                    "calls": row.calls,
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                    "avg_latency_ms": round(row.avg_latency_ms, 1) if row.avg_latency_ms else 0,
                }
                for row in by_feature
            ],
            "by_day": [
                {
                    "date": row.day.isoformat() if row.day else None,
                    "calls": row.calls,
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                }
                for row in by_day
            ],
            "errors_by_feature": [
                {"feature": row.feature, "count": row.error_count}
                for row in errors
            ],
            "recent_errors": [
                {
                    "id": e.id,
                    "feature": e.feature,
                    "error": e.error,
                    "latency_ms": e.latency_ms,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in recent_errors
            ],
        }


# ─── Reports Analytics ──────────────────────────────────────────────────────

@app.get("/api/reports/analytics", dependencies=[Depends(require_auth)])
async def reports_analytics(
    days: int = Query(default=30, ge=1, le=365),
    challenge_id: int | None = Query(default=None),
):
    """Report analytics: daily counts, points distribution, activity breakdown."""
    async with async_session_factory() as session:
        since = date.today() - timedelta(days=days)

        # Base filter
        base = select(DailyReport).where(DailyReport.report_date >= since)
        if challenge_id:
            base = base.join(UserChallenge).where(UserChallenge.challenge_id == challenge_id)

        # Daily report counts
        daily_stmt = (
            select(
                DailyReport.report_date,
                func.count(DailyReport.id).label("count"),
                func.sum(DailyReport.total_points).label("total_points"),
                func.avg(DailyReport.total_points).label("avg_points"),
            )
            .where(DailyReport.report_date >= since)
        )
        if challenge_id:
            daily_stmt = daily_stmt.join(UserChallenge).where(UserChallenge.challenge_id == challenge_id)
        daily_stmt = daily_stmt.group_by(DailyReport.report_date).order_by(DailyReport.report_date)
        daily_rows = (await session.execute(daily_stmt)).all()

        # Activity category breakdown
        cat_stmt = (
            select(
                ReportActivity.category,
                func.count(ReportActivity.id).label("count"),
                func.sum(ReportActivity.points).label("total_points"),
                func.sum(ReportActivity.duration_minutes).label("total_minutes"),
            )
            .join(DailyReport, DailyReport.id == ReportActivity.report_id)
            .where(DailyReport.report_date >= since)
        )
        if challenge_id:
            cat_stmt = cat_stmt.join(UserChallenge).where(UserChallenge.challenge_id == challenge_id)
        cat_stmt = cat_stmt.group_by(ReportActivity.category)
        cat_rows = (await session.execute(cat_stmt)).all()

        return {
            "period_days": days,
            "challenge_id": challenge_id,
            "daily": [
                {
                    "date": row.report_date.isoformat(),
                    "count": row.count,
                    "total_points": row.total_points or 0,
                    "avg_points": round(row.avg_points, 1) if row.avg_points else 0,
                }
                for row in daily_rows
            ],
            "by_category": [
                {
                    "category": row.category,
                    "count": row.count,
                    "total_points": row.total_points or 0,
                    "total_minutes": row.total_minutes or 0,
                }
                for row in cat_rows
            ],
        }


# ─── System ─────────────────────────────────────────────────────────────────

@app.get("/api/system/db", dependencies=[Depends(require_auth)])
async def system_db():
    """Database statistics: table row counts and size."""
    async with async_session_factory() as session:
        tables = [
            "users", "challenges", "user_challenges", "daily_reports",
            "report_activities", "words_of_the_day", "quizzes", "quiz_answers",
            "weekly_battles", "battle_pairs", "conversation_history", "llm_usage_log",
        ]
        counts = {}
        for table in tables:
            result = await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            counts[table] = result.scalar() or 0

        # DB size
        db_size = (await session.execute(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        )).scalar()

        return {
            "table_counts": counts,
            "database_size": db_size,
        }
