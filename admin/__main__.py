"""Entry point for the admin panel: python -m admin."""

import logging
import uvicorn

from admin.config import admin_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    uvicorn.run(
        "admin.app:app",
        host="0.0.0.0",
        port=admin_settings.ADMIN_PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
