from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJob, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.publishers.x_publisher import XPublishResult, XPublisherError
from app.services.retry_service import RetryService


class FakePublisher:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc

    def publish(self, post_job: PostJob) -> XPublishResult:
        if self.exc:
            raise self.exc
        return XPublishResult(x_post_id="x-retry", media_ids=["m-1"])


def test_retry_service_republishes_failed_job(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_failed_publishable_job(session)

        result = RetryService(
            session=session,
            settings=settings,
            publisher=FakePublisher(),
        ).retry_post_job(post_job.id)

        assert result.is_success is True
        assert result.x_post_id == "x-retry"
        assert post_job.status == PostJobStatus.PUBLISHED.value
        assert post_job.x_post_id == "x-retry"


def test_retry_service_keeps_failure_reason_when_publish_fails(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_failed_publishable_job(session)

        result = RetryService(
            session=session,
            settings=settings,
            publisher=FakePublisher(exc=XPublisherError("retry failed")),
        ).retry_post_job(post_job.id)

        assert result.is_success is False
        assert "retry failed" in (result.error_message or "")
        assert post_job.status == PostJobStatus.FAILED.value
        assert "retry failed" in (post_job.error_message or "")


def test_retry_service_rejects_non_failed_job(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_failed_publishable_job(session)
        Repository(session).update_post_job_status(post_job, PostJobStatus.PUBLISHED)

        result = RetryService(
            session=session,
            settings=settings,
            publisher=FakePublisher(),
        ).retry_post_job(post_job.id)

        assert result.is_success is False
        assert "failed状態" in (result.error_message or "")
        assert post_job.status == PostJobStatus.PUBLISHED.value


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)


def _create_failed_publishable_job(session) -> PostJob:
    repository = Repository(session)
    post_job = repository.create_post_job(source_type="telegram")
    media_asset = repository.create_media_asset(
        post_job_id=post_job.id,
        original_path="storage/raw/1/photo.jpg",
        processed_path="storage/processed/1/photo.jpg",
        thumbnail_path="storage/thumbnails/1/photo.jpg",
        media_type="image",
        mime_type="image/jpeg",
        file_hash="hash",
        file_size=123,
        width=640,
        height=480,
        status=MediaAssetStatus.PROCESSED,
    )
    post_job.media_assets.append(media_asset)
    repository.update_post_job_caption(
        post_job,
        caption="投稿本文です",
        hashtags=["#retry"],
        alt_text="代替テキストです",
        ai_warnings=[],
        status=PostJobStatus.CAPTIONED,
    )
    return repository.update_post_job_status(post_job, PostJobStatus.FAILED, error_message="前回投稿失敗")
