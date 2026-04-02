import asyncio
import logging

from bot.app import create_bot, create_dispatcher
from bot.config import settings
from bot.db.engine import async_session_factory
from bot.metrics import BOT_INFO, start_metrics_server
from bot.scheduler.setup import setup_scheduler


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Start Prometheus metrics server (port 9090)
    start_metrics_server(port=9090)
    BOT_INFO.info({"version": "1.0.0", "model": settings.GOOGLE_AI_MODEL})

    bot = create_bot()
    dp = create_dispatcher()

    scheduler = setup_scheduler(bot, async_session_factory)

    logger.info("Starting LangBro bot...")
    try:
        asyncio.run(dp.start_polling(bot))
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
