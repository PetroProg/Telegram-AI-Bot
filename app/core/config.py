from typing import Set
from pydantic import Field
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

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def allowed_users_set(self) -> Set[int]:
        if not self.ALLOWED_USER_IDS:
            return set()
        return {int(uid.strip()) for uid in self.ALLOWED_USER_IDS.split(",") if uid.strip()}


settings = Settings()
