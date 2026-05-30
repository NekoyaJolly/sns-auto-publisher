import json
from pathlib import Path

from sqlalchemy import select

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostAttempt, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.publishers.x_publisher import XPublishResult, XPublisherError, build_x_post_text
from app.services.publish_service import PublishService


class FakePublisher:
    def __init__(self, result: XPublishResult | None = None, exc: Exception | None = None) -> None:
        self.result = result or XPublishResult(x_post_id="x-123", media_ids=["m-1"])
        self.exc = exc

    def publish(self, post_job):
        if self.exc:
            raise self.exc
        return self.result


def test_publish_service_marks_job_published_and_records_attempt(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_publishing_post_job(session, media_count=2)

        result = PublishService(
            session=session,
            settings=settings,
            publisher=FakePublisher(XPublishResult(x_post_id="x-999", media_ids=["m-1", "m-2"])),
        ).publish_post_job(post_job)

        attempts = session.scalars(select(PostAttempt)).all()

        assert result.is_success is True
        assert result.x_post_id == "x-999"
        assert post_job.status == PostJobStatus.PUBLISHED.value
        assert post_job.x_post_id == "x-999"
        assert len(attempts) == 1
        assert attempts[0].provider == "x"
        assert attempts[0].status == "succeeded"
        assert json.loads(attempts[0].response_payload_json or "{}")["media_ids"] == ["m-1", "m-2"]


def test_publish_service_marks_job_failed_and_records_attempt(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_publishing_post_job(session)

        result = PublishService(
            session=session,
            settings=settings,
            publisher=FakePublisher(exc=XPublisherError("X API error")),
        ).publish_post_job(post_job)

        attempts = session.scalars(select(PostAttempt)).all()

        assert result.is_success is False
        assert "X API error" in (result.error_message or "")
        assert post_job.status == PostJobStatus.FAILED.value
        assert "X API error" in (post_job.error_message or "")
        assert len(attempts) == 1
        assert attempts[0].status == "failed"
        assert "X API error" in (attempts[0].error_message or "")


def test_build_x_post_text_includes_caption_and_hashtags(tmp_path: Path):
    _settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_publishing_post_job(session)

        text = build_x_post_text(post_job)

        assert "投稿本文です" in text
        assert "#photo #daily" in text


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)


def _create_publishing_post_job(session, *, media_count: int = 1):
    repository = Repository(session)
    post_job = repository.create_post_job(source_type="telegram")
    for index in range(media_count):
        media_asset = repository.create_media_asset(
            post_job_id=post_job.id,
            original_path=f"storage/raw/1/photo-{index}.jpg",
            processed_path=f"storage/processed/1/photo-{index}.jpg",
            thumbnail_path=f"storage/thumbnails/1/photo-{index}.jpg",
            media_type="image",
            mime_type="image/jpeg",
            file_hash=f"hash-{index}",
            file_size=123,
            width=640,
            height=480,
            status=MediaAssetStatus.PROCESSED,
        )
        post_job.media_assets.append(media_asset)
    repository.update_post_job_caption(
        post_job,
        caption="投稿本文です",
        hashtags=["#photo", "#daily"],
        alt_text="代替テキストです",
        ai_warnings=[],
        status=PostJobStatus.CAPTIONED,
    )
    return repository.update_post_job_status(post_job, PostJobStatus.PUBLISHING)
