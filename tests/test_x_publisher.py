from pathlib import Path
from types import SimpleNamespace

from app.config.settings import Settings
from app.db.models import MediaAssetStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.publishers.x_publisher import XPublisher, XPublisherError


def test_x_publisher_requires_credentials(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )

    try:
        XPublisher(settings)
    except XPublisherError as exc:
        assert "X_API_KEY" in str(exc)
        assert "X_ACCESS_TOKEN_SECRET" in str(exc)
    else:
        raise AssertionError("X認証情報がない場合はXPublisherErrorにする必要があります")


def test_x_publisher_uploads_image_as_tweet_image(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    media_path = tmp_path / "photo.jpg"
    media_path.write_bytes(b"image")
    api = FakeApi()

    with session_scope(session_factory) as session:
        media_asset = _create_media_asset(session, media_path=media_path, media_type="image", mime_type="image/jpeg")
        media_id = XPublisher(settings)._upload_media(api, media_asset)

    assert media_id == "media-123"
    assert api.calls == [{"filename": str(media_path), "media_category": "tweet_image", "chunked": False}]


def test_x_publisher_uploads_video_as_chunked_tweet_video(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    media_path = tmp_path / "movie.mp4"
    media_path.write_bytes(b"video")
    api = FakeApi()

    with session_scope(session_factory) as session:
        media_asset = _create_media_asset(session, media_path=media_path, media_type="video", mime_type="video/mp4")
        media_id = XPublisher(settings)._upload_media(api, media_asset)

    assert media_id == "media-123"
    assert api.calls == [{"filename": str(media_path), "media_category": "tweet_video", "chunked": True}]


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def media_upload(self, *, filename: str, media_category: str, chunked: bool):
        self.calls.append(
            {
                "filename": filename,
                "media_category": media_category,
                "chunked": chunked,
            }
        )
        return SimpleNamespace(media_id_string="media-123")


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        x_api_key="key",
        x_api_secret="secret",
        x_access_token="token",
        x_access_token_secret="token-secret",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)


def _create_media_asset(session, *, media_path: Path, media_type: str, mime_type: str):
    repository = Repository(session)
    post_job = repository.create_post_job(source_type="telegram")
    return repository.create_media_asset(
        post_job_id=post_job.id,
        original_path=str(media_path),
        processed_path=str(media_path),
        thumbnail_path=str(media_path),
        media_type=media_type,
        mime_type=mime_type,
        file_hash="hash",
        file_size=media_path.stat().st_size,
        status=MediaAssetStatus.PROCESSED,
    )
