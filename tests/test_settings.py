from app.config.settings import Settings
from app.db.models import PostingMode


def test_settings_can_be_loaded(monkeypatch):
    monkeypatch.delenv("POSTING_MODE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_env == "local"
    assert settings.database_url == "sqlite:///data/app.sqlite3"


def test_posting_mode_default_is_approval(monkeypatch):
    monkeypatch.delenv("POSTING_MODE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.posting_mode == PostingMode.APPROVAL
