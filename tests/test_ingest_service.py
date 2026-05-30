from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostingMode
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.storage.local_storage import LocalStorage


def test_ingest_service_saves_raw_files_and_registers_db_records(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    storage = LocalStorage(settings=settings)

    with session_scope(session_factory) as session:
        service = IngestService(session=session, storage=storage, settings=settings)
        result = service.ingest_telegram_media(
            chat_id="12345",
            user_id="67890",
            media_files=[
                IncomingMediaFile(
                    filename="photo.jpg",
                    content=b"image bytes",
                    media_type="image",
                    mime_type="image/jpeg",
                ),
                IncomingMediaFile(
                    filename="movie.mp4",
                    content=b"video bytes",
                    media_type="video",
                    mime_type="video/mp4",
                ),
            ],
        )

        assert result.post_job.id is not None
        assert result.post_job.source_type == "telegram"
        assert result.post_job.mode == PostingMode.APPROVAL.value
        assert len(result.media_assets) == 2
        for media_asset in result.media_assets:
            assert media_asset.status == MediaAssetStatus.RECEIVED.value
            assert media_asset.file_hash
            assert Path(media_asset.original_path).exists()


def test_ingest_service_rejects_empty_media_files(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    storage = LocalStorage(settings=settings)

    with session_scope(session_factory) as session:
        service = IngestService(session=session, storage=storage, settings=settings)

        try:
            service.ingest_telegram_media(chat_id="12345", user_id=None, media_files=[])
        except ValueError as exc:
            assert "media_files" in str(exc)
        else:
            raise AssertionError("media_filesが空ならValueErrorにする必要があります")
