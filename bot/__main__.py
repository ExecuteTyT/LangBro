import asyncio
import logging

from bot.app import create_bot, create_dispatcher
from bot.config import settings


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger = logging.getLogger(__name__)

    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Starting LangBro bot...")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
