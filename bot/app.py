import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.db.engine import async_session_factory
from bot.handlers import start, challenge, report, stats, quiz, pronounce, coach, admin, profile
from bot.middlewares.db_session import DbSessionMiddleware
from bot.middlewares.user_registration import UserRegistrationMiddleware
from bot.middlewares.challenge_context import ChallengeContextMiddleware

logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Register middlewares (order matters: db → user → challenge)
    dp.message.middleware(DbSessionMiddleware(async_session_factory))
    dp.callback_query.middleware(DbSessionMiddleware(async_session_factory))

    dp.message.middleware(UserRegistrationMiddleware())
    dp.callback_query.middleware(UserRegistrationMiddleware())

    dp.message.middleware(ChallengeContextMiddleware())
    dp.callback_query.middleware(ChallengeContextMiddleware())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(challenge.router)
    dp.include_router(report.router)
    dp.include_router(stats.router)
    dp.include_router(quiz.router)
    dp.include_router(pronounce.router)
    dp.include_router(coach.router)
    dp.include_router(admin.router)
    dp.include_router(profile.router)

    return dp
