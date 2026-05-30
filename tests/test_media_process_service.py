from pathlib import Path

from PIL import Image

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.media_process_service import MediaProcessService
from app.services.validation_service import ValidationService
from app.storage.local_storage import LocalStorage


def test_media_process_service_resizes_image_and_generates_thumbnail(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    image_bytes = _image_bytes_with_exif(tmp_path / "source.jpg", size=(1800, 1200))

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
        ValidationService(session=session, settings=settings).validate_post_job(result.post_job)

        process_service = MediaProcessService(
            session=session,
            storage=storage,
            max_image_side=800,
            thumbnail_side=240,
        )
        processed_assets = process_service.process_post_job_images(result.post_job)
        media_asset = processed_assets[0]

        assert result.post_job.status == PostJobStatus.PROCESSED.value
        assert media_asset.status == MediaAssetStatus.PROCESSED.value
        assert media_asset.processed_path is not None
        assert media_asset.thumbnail_path is not None

    processed_path = Path(media_asset.processed_path)
    thumbnail_path = Path(media_asset.thumbnail_path)
    assert processed_path.exists()
    assert thumbnail_path.exists()

    with Image.open(processed_path) as processed_image:
        assert max(processed_image.size) == 800
        assert "exif" not in processed_image.info
    with Image.open(thumbnail_path) as thumbnail_image:
        assert max(thumbnail_image.size) <= 240


def test_media_process_service_requires_validated_image(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    image_bytes = _image_bytes_with_exif(tmp_path / "source.jpg", size=(640, 480))

    with session_scope(session_factory) as session:
        ingest_service = IngestService(session=session, storage=storage, settings=settings)
        result = ingest_service.ingest_telegram_media(
            chat_id="12345",
            user_id=None,
            media_files=[
                IncomingMediaFile(
                    filename="photo.jpg",
                    content=image_bytes,
                    media_type="image",
                    mime_type="image/jpeg",
                )
            ],
        )

        process_service = MediaProcessService(session=session, storage=storage)
        try:
            process_service.process_image_asset(result.media_assets[0])
        except ValueError as exc:
            assert "validated" in str(exc)
        else:
            raise AssertionError("validated前の画像処理はValueErrorにする必要があります")


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


def _image_bytes_with_exif(path: Path, *, size: tuple[int, int]) -> bytes:
    image = Image.new("RGB", size, (200, 80, 40))
    exif = Image.Exif()
    exif[274] = 1
    image.save(path, format="JPEG", exif=exif)
    return path.read_bytes()
