"""APScheduler setup: registers all cron jobs."""

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.scheduler.jobs import (
    battle_create_job,
    battle_resolve_job,
    daily_digest_job,
    quiz_schedule_job,
    reminder_job,
    weekly_digest_job,
    wotd_job,
)

logger = logging.getLogger(__name__)


def setup_scheduler(
    bot: Bot,
    session_factory: async_sessionmaker,
) -> AsyncIOScheduler:
    """Create and start APScheduler with all cron jobs."""
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    common = {"bot": bot, "session_factory": session_factory}

    # Word of the Day — 08:00 MSK daily
    scheduler.add_job(
        wotd_job, "cron", hour=8, minute=0,
        kwargs=common,
        id="wotd", replace_existing=True,
    )

    # Quiz scheduler — 12:00 MSK daily (picks random time 12:00-15:00)
    scheduler.add_job(
        quiz_schedule_job, "cron", hour=12, minute=0,
        kwargs={**common, "scheduler": scheduler},
        id="quiz_scheduler", replace_existing=True,
    )

    # Reminder — 20:00 MSK daily
    scheduler.add_job(
        reminder_job, "cron", hour=20, minute=0,
        kwargs=common,
        id="reminder", replace_existing=True,
    )

    # Daily Digest — 22:00 MSK daily
    scheduler.add_job(
        daily_digest_job, "cron", hour=22, minute=0,
        kwargs=common,
        id="daily_digest", replace_existing=True,
    )

    # Weekly Battle create — Monday 09:00 MSK
    scheduler.add_job(
        battle_create_job, "cron", day_of_week="mon", hour=9, minute=0,
        kwargs=common,
        id="battle_create", replace_existing=True,
    )

    # Weekly Battle resolve — Friday 19:00 MSK
    scheduler.add_job(
        battle_resolve_job, "cron", day_of_week="fri", hour=19, minute=0,
        kwargs=common,
        id="battle_resolve", replace_existing=True,
    )

    # Weekly Digest — Sunday 12:00 MSK
    scheduler.add_job(
        weekly_digest_job, "cron", day_of_week="sun", hour=12, minute=0,
        kwargs=common,
        id="weekly_digest", replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started with %d jobs: %s",
        len(scheduler.get_jobs()),
        ", ".join(j.id for j in scheduler.get_jobs()),
    )
    return scheduler
