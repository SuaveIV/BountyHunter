import os

from pydantic import BaseModel, ValidationError, field_validator


class Settings(BaseModel):
    BOT_TOKEN: str
    DATABASE_PATH: str = "./data/bountyhunter.db"
    POLL_INTERVAL: int = 30
    ADMIN_DISCORD_ID: str = ""
    LOG_LEVEL: str = "INFO"
    ITAD_API_KEY: str = ""

    @field_validator("BOT_TOKEN")
    @classmethod
    def token_not_empty(cls, v):
        if not v:
            raise ValueError("BOT_TOKEN is required")
        return v


try:
    _settings = Settings(
        BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
        DATABASE_PATH=os.getenv("DATABASE_PATH", "./data/bountyhunter.db"),
        POLL_INTERVAL=int(os.getenv("POLL_INTERVAL", "30")),
        ADMIN_DISCORD_ID=os.getenv("ADMIN_DISCORD_ID", ""),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
        ITAD_API_KEY=os.getenv("ITAD_API_KEY", ""),
    )
except ValidationError as e:
    raise RuntimeError(f"Configuration Error: {e}") from e

# Export variables to maintain compatibility with existing imports
BOT_TOKEN = _settings.BOT_TOKEN
DATABASE_PATH = _settings.DATABASE_PATH
POLL_INTERVAL = _settings.POLL_INTERVAL
ADMIN_DISCORD_ID = _settings.ADMIN_DISCORD_ID
LOG_LEVEL = _settings.LOG_LEVEL
ITAD_API_KEY = _settings.ITAD_API_KEY
