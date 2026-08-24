"""Application-level configuration loaded from environment variables and .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration container for the trading bot.

    All values are sourced from environment variables or a ``.env`` file
    via pydantic-settings.  Sensible defaults are provided for local
    development (testnet mode, 20x leverage, 70 % confidence threshold).
    """

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: int = 0

    DEFAULT_LEVERAGE: int = 20
    CONFIDENCE_THRESHOLD: float = 0.70

    DATABASE_URL: str = ""

    LOG_LEVEL: str = "INFO"

    # JWT Authentication & Admin Defaults
    JWT_SECRET_KEY: str = "dev-secret-jwt-key-replace-in-production-0987654321"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEFAULT_ADMIN_USERNAME: str = "admin"
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()