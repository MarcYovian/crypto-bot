"""Application-level configuration loaded from environment variables and .env file."""

from typing import List, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration container for the trading bot.

    All values are sourced from environment variables or a ``.env`` file
    via pydantic-settings. Sensible defaults are provided for local
    development (testnet mode, 20x leverage, 70 % confidence threshold).
    """

    ENVIRONMENT: str = "development"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: int = 0
    TELEGRAM_APP_ID: int = 0
    TELEGRAM_APP_HASH: str = ""

    DEFAULT_LEVERAGE: int = 20
    CONFIDENCE_THRESHOLD: float = 0.70

    DATABASE_URL: str = ""

    LOG_LEVEL: str = "INFO"
    WS_CACHE_LOG_PATH: str = "/var/log/cryptobot/wsbinance/"

    # CORS Origins (list of allowed origins or comma-separated string)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # API Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 120

    # Risk & Pre-Trade Margin Management
    AUTO_MARGIN_CAPPING: bool = True
    MARGIN_SAFETY_BUFFER: float = 0.95

    # JWT Authentication & Admin Defaults
    JWT_SECRET_KEY: str = "dev-secret-jwt-key-replace-in-production-0987654321"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "AdminPassword123!"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.strip() == "*":
                return ["*"]
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, set, tuple)):
            return [str(i).strip() for i in v if str(i).strip()]
        return []

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        is_prod = str(self.ENVIRONMENT).strip().lower() in ("production", "prod")
        if is_prod:
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY.startswith("dev-secret-"):
                raise ValueError("JWT_SECRET_KEY must be securely set in production mode and cannot use dev default.")
            if not self.DEFAULT_ADMIN_PASSWORD or self.DEFAULT_ADMIN_PASSWORD == "AdminPassword123!":
                raise ValueError("DEFAULT_ADMIN_PASSWORD must be explicitly provided in production mode and cannot use default.")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("CORS wildcard ('*') is not allowed in production mode. Specify explicit frontend origins.")
        return self

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()