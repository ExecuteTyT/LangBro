import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User
from bot.db.repositories.challenge_repo import ChallengeRepository

logger = logging.getLogger(__name__)


class ChallengeContextMiddleware(BaseMiddleware):
    """Resolves the active challenge for the current event.

    - Group chat: by chat_id
    - Private chat: by active_challenge_id (auto-select if only one)
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        db_user: User | None = data.get("db_user")
        repo = ChallengeRepository(session)

        challenge = None
        chat = None

        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat

        if chat and chat.type != "private":
            # Group: resolve by chat_id
            challenge = await repo.get_active_by_chat(chat.id)
        elif db_user:
            # Private: resolve by user's challenges
            active_challenges = await repo.get_user_active_challenges(db_user.id)
            if len(active_challenges) == 1:
                challenge = active_challenges[0]
                # Auto-set active_challenge_id
                if db_user.active_challenge_id != challenge.id:
                    db_user.active_challenge_id = challenge.id
                    await session.flush()
            elif db_user.active_challenge_id:
                challenge = await repo.get_by_id(db_user.active_challenge_id)

        data["challenge"] = challenge
        data["challenge_repo"] = repo

        return await handler(event, data)
