"""Scheduled jobs: daily_digest, reminder, wotd, quiz, battles, weekly digest, vacation reset."""

import logging
import random
import time as _time
from datetime import datetime, timedelta, timezone
from functools import wraps

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Challenge
from bot.llm.client import GeminiClient
from bot.metrics import SCHEDULER_JOB_DURATION, SCHEDULER_JOB_RUNS
from bot.services.digest_service import DigestService

logger = logging.getLogger(__name__)


def _track_job(job_name: str):
    """Decorator that tracks scheduler job execution in Prometheus."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = _time.monotonic()
            try:
                result = await func(*args, **kwargs)
                SCHEDULER_JOB_RUNS.labels(job=job_name, status="success").inc()
                return result
            except Exception:
                SCHEDULER_JOB_RUNS.labels(job=job_name, status="error").inc()
                raise
            finally:
                elapsed = _time.monotonic() - start
                SCHEDULER_JOB_DURATION.labels(job=job_name).observe(elapsed)
        return wrapper
    return decorator


async def _iter_active_challenges(session_factory, feature_key=None):
    """Yield (session, challenge) for active challenges matching criteria."""
    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())

        today = datetime.now(timezone.utc).date()
        for challenge in challenges:
            if feature_key:
                features = challenge.features_enabled or {}
                if not features.get(feature_key, True):
                    continue
            schedule = challenge.schedule_days or [1, 2, 3, 4, 5]
            if today.isoweekday() not in schedule:
                continue
            yield session, challenge
        await session.commit()


@_track_job("daily_digest")
async def daily_digest_job(bot: Bot, session_factory: async_sessionmaker) -> None:
    logger.info("Running daily_digest_job")
    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())
        today = datetime.now(timezone.utc).date()

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("daily_digest", True):
                continue
            if today.isoweekday() not in (challenge.schedule_days or [1, 2, 3, 4, 5]):
                continue
            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = DigestService(session, gemini)
                text = await service.generate_daily_digest(challenge)
                if text:
                    await bot.send_message(challenge.chat_id, text)
            except Exception as e:
                logger.exception("Digest failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("reminder")
async def reminder_job(bot: Bot, session_factory: async_sessionmaker) -> None:
    logger.info("Running reminder_job")
    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())
        today = datetime.now(timezone.utc).date()

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("reminders", True):
                continue
            if today.isoweekday() not in (challenge.schedule_days or [1, 2, 3, 4, 5]):
                continue
            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = DigestService(session, gemini)
                text = await service.generate_reminder(challenge)
                if text:
                    await bot.send_message(challenge.chat_id, text)
            except Exception as e:
                logger.exception("Reminder failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("wotd")
async def wotd_job(bot: Bot, session_factory: async_sessionmaker) -> None:
    """Send Word of the Day to all active challenges."""
    logger.info("Running wotd_job")
    from bot.services.wotd_service import WotdService

    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())
        today = datetime.now(timezone.utc).date()

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("word_of_day", True):
                continue
            if today.isoweekday() not in (challenge.schedule_days or [1, 2, 3, 4, 5]):
                continue
            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = WotdService(session, gemini)
                await service.generate_and_send(challenge, bot)
            except Exception as e:
                logger.exception("WotD failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("quiz_schedule")
async def quiz_schedule_job(
    bot: Bot,
    session_factory: async_sessionmaker,
    scheduler: AsyncIOScheduler,
) -> None:
    """Called at 12:00 — schedules the actual quiz at a random time 12:00-15:00."""
    offset_minutes = random.randint(0, 180)
    run_at = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    logger.info("Scheduling quiz_job at %s (offset=%d min)", run_at, offset_minutes)

    scheduler.add_job(
        quiz_job,
        "date",
        run_date=run_at,
        kwargs={"bot": bot, "session_factory": session_factory, "scheduler": scheduler},
        id=f"quiz_run_{run_at.strftime('%Y%m%d')}",
        replace_existing=True,
    )


@_track_job("quiz")
async def quiz_job(
    bot: Bot,
    session_factory: async_sessionmaker,
    scheduler: AsyncIOScheduler,
) -> None:
    """Generate and send a pop quiz, schedule auto-close in 30 min."""
    logger.info("Running quiz_job")
    from bot.services.quiz_service import QuizService

    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())
        today = datetime.now(timezone.utc).date()

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("pop_quiz", True):
                continue
            if today.isoweekday() not in (challenge.schedule_days or [1, 2, 3, 4, 5]):
                continue
            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = QuizService(session, gemini)
                quiz = await service.generate_and_send(challenge, bot)

                # Schedule auto-close in 30 minutes
                close_at = datetime.now(timezone.utc) + timedelta(minutes=30)
                scheduler.add_job(
                    quiz_close_job,
                    "date",
                    run_date=close_at,
                    kwargs={
                        "bot": bot,
                        "session_factory": session_factory,
                        "quiz_id": quiz.id,
                    },
                    id=f"quiz_close_{quiz.id}",
                    replace_existing=True,
                )
            except Exception as e:
                logger.exception("Quiz failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("quiz_close")
async def quiz_close_job(
    bot: Bot, session_factory: async_sessionmaker, quiz_id: int
) -> None:
    """Close a specific quiz and post results."""
    logger.info("Running quiz_close_job for quiz %s", quiz_id)
    from bot.services.quiz_service import QuizService

    async with session_factory() as session:
        gemini = GeminiClient(session_factory=session_factory)
        service = QuizService(session, gemini)
        await service.close_quiz(quiz_id, bot)
        await session.commit()


@_track_job("battle_create")
async def battle_create_job(
    bot: Bot, session_factory: async_sessionmaker
) -> None:
    """Monday: create weekly battle pairs."""
    logger.info("Running battle_create_job")
    from bot.services.battle_service import BattleService

    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("weekly_battles", True):
                continue
            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = BattleService(session, gemini)
                await service.create_weekly_battle(challenge, bot)
            except Exception as e:
                logger.exception("Battle create failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("battle_resolve")
async def battle_resolve_job(
    bot: Bot, session_factory: async_sessionmaker
) -> None:
    """Friday: resolve weekly battles and post results."""
    logger.info("Running battle_resolve_job")
    from bot.services.battle_service import BattleService

    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("weekly_battles", True):
                continue
            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = BattleService(session, gemini)
                await service.resolve_weekly_battle(challenge, bot)
            except Exception as e:
                logger.exception("Battle resolve failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("weekly_digest")
async def weekly_digest_job(
    bot: Bot, session_factory: async_sessionmaker
) -> None:
    """Sunday: send weekly digest."""
    logger.info("Running weekly_digest_job")
    from bot.services.weekly_digest_service import WeeklyDigestService

    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("weekly_digest", True):
                continue
            try:
                service = WeeklyDigestService(session)
                text = await service.generate_weekly_digest(challenge)
                if text:
                    await bot.send_message(challenge.chat_id, text)
            except Exception as e:
                logger.exception("Weekly digest failed for challenge %s: %s", challenge.id, e)
        await session.commit()


@_track_job("vacation_reset")
async def vacation_reset_job(session_factory: async_sessionmaker) -> None:
    """Monthly: reset vacation_days_used for all participants on the 1st."""
    logger.info("Running vacation_reset_job")
    from bot.db.repositories.challenge_repo import ChallengeRepository

    async with session_factory() as session:
        repo = ChallengeRepository(session)
        all_ucs = await repo.get_all_active_user_challenges()
        count = 0
        for uc in all_ucs:
            if uc.vacation_days_used > 0:
                uc.vacation_days_used = 0
                count += 1
        await session.commit()
        logger.info("Vacation reset: cleared %d user records", count)
