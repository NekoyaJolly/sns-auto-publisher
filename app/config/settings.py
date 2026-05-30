from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.db.models import PostingMode


class Settings(BaseSettings):
    app_env: str = "local"
    posting_mode: PostingMode = PostingMode.APPROVAL

    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)

    openai_api_key: str = ""
    openai_model: str = ""

    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""
    x_bearer_token: str = ""

    database_url: str = "sqlite:///data/app.sqlite3"
    storage_root: Path = Path("storage")
    max_image_size_mb: int = 10
    max_video_size_mb: int = 512
    max_video_duration_seconds: int = 140

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def split_allowed_chat_ids(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item) for item in value]
        raise TypeError("TELEGRAM_ALLOWED_CHAT_IDSはカンマ区切り文字列または配列で指定してください")


@lru_cache
def get_settings() -> Settings:
    return Settings()
