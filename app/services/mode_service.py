from __future__ import annotations

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import PostingMode
from app.db.repository import Repository


class ModeService:
    setting_key = "posting_mode"

    def __init__(self, session: Session, settings: Settings) -> None:
        self.repository = Repository(session)
        self.settings = settings

    def get_mode(self) -> PostingMode:
        setting = self.repository.get_app_setting(self.setting_key)
        if setting is None:
            return self.settings.posting_mode
        return PostingMode(setting.value)

    def set_mode(self, mode: PostingMode | str) -> PostingMode:
        posting_mode = PostingMode(mode)
        self.repository.set_app_setting(self.setting_key, posting_mode.value)
        return posting_mode


def posting_mode_help_text(current_mode: PostingMode) -> str:
    return (
        f"現在の投稿モード: {current_mode.value}\n"
        "変更する場合は `/mode approval` / `/mode auto` / `/mode dry_run` のいずれかを送ってください。"
    )
