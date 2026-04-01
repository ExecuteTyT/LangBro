from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    TELEGRAM_BOT_TOKEN: str

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://langbro:langbro_dev@localhost:5432/langbro"
    )

    # Google AI Studio
    GOOGLE_AI_API_KEY: str = ""
    GOOGLE_AI_MODEL: str = "gemini-2.5-flash"

    # App settings
    DEFAULT_TIMEZONE: str = "Europe/Moscow"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False


settings = Settings()  # type: ignore[call-arg]
