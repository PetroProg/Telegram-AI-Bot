from typing import Any, Optional, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram
    BOT_TOKEN: str = Field(default="", description="Telegram Bot Token from @BotFather")
    ALLOWED_USER_IDS: str = Field(default="", description="Comma-separated Telegram user IDs (empty = allow all)")

    # Database
    DB_HOST: str = Field(default="news_ai_postgres", description="Database host")
    DB_PORT: int = Field(default=5432, description="Database port")
    DB_NAME: str = Field(default="tg_ai_bot", description="Database name")
    DB_USER: str = Field(default="tg_ai_user", description="Database user")
    DB_PASSWORD: str = Field(default="", description="Database password")

    # LLM Keys
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API Key")
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API Key")
    AI_HORDE_API_KEY: str = Field(default="0000000000", description="AI Horde Key (0000000000 for anonymous)")

    # Defaults
    DEFAULT_CONTEXT_LIMIT: int = 10
    LOG_LEVEL: str = "INFO"

    # Weekly Report Settings
    WEEKLY_REPORT_ENABLED: bool = Field(default=True, description="Enable automatic weekly usage report")
    REPORT_CHAT_ID: Optional[int] = Field(
        default=None,
        description="Recipient Telegram chat ID (defaults to owner_user_id)",
    )
    REPORT_TIMEZONE: str = Field(default="Europe/Zurich", description="IANA timezone for weekly report schedule")
    WEEKLY_REPORT_DAY: int = Field(default=6, ge=0, le=6, description="Day of week (0=Mon .. 6=Sun)")
    WEEKLY_REPORT_HOUR: int = Field(default=12, ge=0, le=23, description="Hour of report delivery (0-23)")
    WEEKLY_REPORT_MINUTE: int = Field(default=0, ge=0, le=59, description="Minute of report delivery (0-59)")

    @field_validator("REPORT_CHAT_ID", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("REPORT_TIMEZONE")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {value}") from exc
        return value

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def allowed_users_set(self) -> Set[int]:
        if not self.ALLOWED_USER_IDS:
            return set()
        return {int(uid.strip()) for uid in self.ALLOWED_USER_IDS.split(",") if uid.strip()}

    @property
    def owner_user_id(self) -> Optional[int]:
        if not self.ALLOWED_USER_IDS:
            return None
        for uid in self.ALLOWED_USER_IDS.split(","):
            if uid.strip():
                return int(uid.strip())
        return None

    @property
    def effective_report_chat_id(self) -> Optional[int]:
        return self.REPORT_CHAT_ID or self.owner_user_id


settings = Settings()
