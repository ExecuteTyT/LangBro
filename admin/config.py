"""Admin panel configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (same as bot)
    DATABASE_URL: str = (
        "postgresql+asyncpg://langbro:langbro_dev@localhost:5432/langbro"
    )

    # Admin auth
    ADMIN_SECRET: str = "changeme"

    # App
    ADMIN_PORT: int = 8000
    DEBUG: bool = False


admin_settings = AdminSettings()  # type: ignore[call-arg]
