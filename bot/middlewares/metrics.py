"""Middleware that tracks Telegram message/callback metrics in Prometheus."""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bot.metrics import TELEGRAM_CALLBACKS, TELEGRAM_COMMANDS, TELEGRAM_MESSAGES

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseMiddleware):
    """Counts incoming messages, commands, and callback queries."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            chat_type = event.chat.type if event.chat else "unknown"
            TELEGRAM_MESSAGES.labels(chat_type=chat_type).inc()

            # Track commands
            if event.text and event.text.startswith("/"):
                command = event.text.split()[0].split("@")[0].lower()
                TELEGRAM_COMMANDS.labels(command=command).inc()

        elif isinstance(event, CallbackQuery):
            TELEGRAM_CALLBACKS.inc()

        return await handler(event, data)
