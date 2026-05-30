from pathlib import Path

from app.config.settings import Settings
from app.db.models import PostingMode
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.mode_service import ModeService, posting_mode_help_text


def test_mode_service_uses_settings_default(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path, PostingMode.APPROVAL)

    with session_scope(session_factory) as session:
        mode = ModeService(session=session, settings=settings).get_mode()

        assert mode == PostingMode.APPROVAL


def test_mode_service_persists_selected_mode(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path, PostingMode.APPROVAL)

    with session_scope(session_factory) as session:
        service = ModeService(session=session, settings=settings)
        service.set_mode("dry_run")

    with session_scope(session_factory) as session:
        mode = ModeService(session=session, settings=settings).get_mode()

        assert mode == PostingMode.DRY_RUN


def test_posting_mode_help_text_contains_current_mode():
    text = posting_mode_help_text(PostingMode.AUTO)

    assert "auto" in text
    assert "/mode approval" in text


def _build_context(tmp_path: Path, posting_mode: PostingMode):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        posting_mode=posting_mode,
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)
