from pathlib import Path

from PIL import Image

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.validation_service import ValidationService
from app.storage.local_storage import LocalStorage


def test_validation_service_validates_image_and_updates_metadata(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    image_bytes = _image_bytes(tmp_path / "source.jpg", size=(640, 480))

    with session_scope(session_factory) as session:
        ingest_service = IngestService(session=session, storage=storage, settings=settings)
        result = ingest_service.ingest_telegram_media(
            chat_id="12345",
            user_id="67890",
            media_files=[
                IncomingMediaFile(
                    filename="photo.jpg",
                    content=image_bytes,
                    media_type="image",
                    mime_type="image/jpeg",
                )
            ],
        )

        validation_service = ValidationService(session=session, settings=settings)
        validation_results = validation_service.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is True
        assert result.post_job.status == PostJobStatus.VALIDATED.value
        assert result.media_assets[0].status == MediaAssetStatus.VALIDATED.value
        assert result.media_assets[0].width == 640
        assert result.media_assets[0].height == 480


def test_validation_service_rejects_non_media_mime(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        ingest_service = IngestService(session=session, storage=storage, settings=settings)
        result = ingest_service.ingest_telegram_media(
            chat_id="12345",
            user_id=None,
            media_files=[
                IncomingMediaFile(
                    filename="note.txt",
                    content=b"plain text",
                    media_type="image",
                    mime_type="text/plain",
                )
            ],
        )

        validation_service = ValidationService(session=session, settings=settings)
        validation_results = validation_service.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.post_job.status == PostJobStatus.FAILED.value
        assert result.media_assets[0].status == MediaAssetStatus.REJECTED.value
        assert "画像または動画以外" in (result.media_assets[0].error_message or "")


def test_validation_service_marks_broken_image_as_failed(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        ingest_service = IngestService(session=session, storage=storage, settings=settings)
        result = ingest_service.ingest_telegram_media(
            chat_id="12345",
            user_id=None,
            media_files=[
                IncomingMediaFile(
                    filename="broken.jpg",
                    content=b"not an image",
                    media_type="image",
                    mime_type="image/jpeg",
                )
            ],
        )

        validation_service = ValidationService(session=session, settings=settings)
        validation_results = validation_service.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.media_assets[0].status == MediaAssetStatus.FAILED.value
        assert "読み取れません" in (result.media_assets[0].error_message or "")


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    storage = LocalStorage(settings=settings)
    return settings, session_factory, storage


def _image_bytes(path: Path, *, size: tuple[int, int]) -> bytes:
    image = Image.new("RGB", size, (24, 120, 180))
    image.save(path, format="JPEG")
    return path.read_bytes()
