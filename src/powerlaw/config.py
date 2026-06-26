from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://powerlaw:powerlaw@localhost:5434/powerlaw"
    storage_dir: Path = Path("storage")
    extraction_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    process_uploads_inline: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4"


@lru_cache
def get_settings() -> Settings:
    return Settings()
