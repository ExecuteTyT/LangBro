"""Database engine for admin panel — shares the same Postgres as the bot."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.config import admin_settings

engine = create_async_engine(
    admin_settings.DATABASE_URL,
    echo=admin_settings.DEBUG,
    pool_size=5,
    max_overflow=5,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
