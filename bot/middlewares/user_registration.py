import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


class UserRegistrationMiddleware(BaseMiddleware):
    """Auto-registers users on first contact (creates a users row)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Message) and event.from_user:
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg_user = event.from_user

        if tg_user and not tg_user.is_bot:
            session: AsyncSession = data["session"]
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(tg_user.id)
            if user is None:
                user = await repo.create(
                    telegram_id=tg_user.id,
                    first_name=tg_user.first_name,
                    username=tg_user.username,
                )
                logger.info("Auto-registered user %s (tg_id=%d)", tg_user.first_name, tg_user.id)
            else:
                # Update username/first_name if changed
                changed = False
                if user.username != tg_user.username:
                    user.username = tg_user.username
                    changed = True
                if user.first_name != tg_user.first_name:
                    user.first_name = tg_user.first_name
                    changed = True
                if changed:
                    await session.flush()

            data["db_user"] = user

        return await handler(event, data)
