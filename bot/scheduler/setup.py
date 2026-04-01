"""APScheduler setup: registers cron jobs for digest and reminders."""

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.scheduler.jobs import daily_digest_job, reminder_job

logger = logging.getLogger(__name__)


def setup_scheduler(
    bot: Bot,
    session_factory: async_sessionmaker,
) -> AsyncIOScheduler:
    """Create and start APScheduler with cron jobs."""
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Daily digest at 22:00 MSK
    scheduler.add_job(
        daily_digest_job,
        "cron",
        hour=22,
        minute=0,
        kwargs={"bot": bot, "session_factory": session_factory},
        id="daily_digest",
        replace_existing=True,
    )

    # Reminder at 20:00 MSK
    scheduler.add_job(
        reminder_job,
        "cron",
        hour=20,
        minute=0,
        kwargs={"bot": bot, "session_factory": session_factory},
        id="reminder",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with jobs: daily_digest (22:00), reminder (20:00)")
    return scheduler
