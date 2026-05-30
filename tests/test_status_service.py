from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.status_service import StatusService


def test_status_service_builds_job_status_text(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        repository = Repository(session)
        post_job = repository.create_post_job(source_type="telegram", status=PostJobStatus.PUBLISHED)
        repository.create_media_asset(
            post_job_id=post_job.id,
            original_path="storage/raw/1/photo.jpg",
            processed_path="storage/processed/1/photo.jpg",
            thumbnail_path="storage/thumbnails/1/photo.jpg",
            media_type="image",
            mime_type="image/jpeg",
            file_hash="hash",
            file_size=123,
            status=MediaAssetStatus.PROCESSED,
        )
        repository.update_post_job_published(post_job, x_post_id="x-123")
        repository.create_post_attempt(post_job_id=post_job.id, provider="x", status="succeeded")

        text = StatusService(session).build_status_text(post_job.id)

        assert f"job_id={post_job.id}" in text
        assert "status=published" in text
        assert "media=1" in text
        assert "x_post_id=x-123" in text
        assert "media_status:" in text
        assert "latest_attempt=x:succeeded" in text
