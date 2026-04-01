"""Scheduled jobs: daily_digest, reminder."""

import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.models import Challenge
from bot.llm.client import GeminiClient
from bot.services.digest_service import DigestService

logger = logging.getLogger(__name__)


async def daily_digest_job(
    bot: Bot,
    session_factory: async_sessionmaker,
) -> None:
    """Send daily digest to all active challenges."""
    logger.info("Running daily_digest_job")
    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("daily_digest", True):
                continue

            # Check if today is a scheduled day
            today = datetime.now(timezone.utc).date()
            if today.isoweekday() not in (challenge.schedule_days or [1, 2, 3, 4, 5]):
                continue

            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = DigestService(session, gemini)
                text = await service.generate_daily_digest(challenge)
                if text:
                    await bot.send_message(challenge.chat_id, text)
                    logger.info("Sent digest to chat %s", challenge.chat_id)
            except Exception as e:
                logger.exception(
                    "Failed to send digest for challenge %s: %s",
                    challenge.id, e,
                )
        await session.commit()


async def reminder_job(
    bot: Bot,
    session_factory: async_sessionmaker,
) -> None:
    """Send reminders to active challenges."""
    logger.info("Running reminder_job")
    async with session_factory() as session:
        stmt = select(Challenge).where(Challenge.status == "active")
        result = await session.execute(stmt)
        challenges = list(result.scalars().all())

        for challenge in challenges:
            features = challenge.features_enabled or {}
            if not features.get("reminders", True):
                continue

            today = datetime.now(timezone.utc).date()
            if today.isoweekday() not in (challenge.schedule_days or [1, 2, 3, 4, 5]):
                continue

            try:
                gemini = GeminiClient(session_factory=session_factory)
                service = DigestService(session, gemini)
                text = await service.generate_reminder(challenge)
                if text:
                    await bot.send_message(challenge.chat_id, text)
                    logger.info("Sent reminder to chat %s", challenge.chat_id)
            except Exception as e:
                logger.exception(
                    "Failed to send reminder for challenge %s: %s",
                    challenge.id, e,
                )
        await session.commit()
