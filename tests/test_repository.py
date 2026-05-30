from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus, PostingMode
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope


def test_repository_can_create_post_job_and_media_asset(tmp_path: Path):
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
        post_job = repository.create_post_job(
            source_type="telegram",
            source_chat_id="12345",
            source_user_id="67890",
        )
        media_asset = repository.create_media_asset(
            post_job_id=post_job.id,
            original_path="storage/raw/1/photo.jpg",
            media_type="image",
            mime_type="image/jpeg",
            file_hash="dummyhash",
            file_size=1024,
            width=1200,
            height=800,
        )

        assert post_job.id is not None
        assert post_job.mode == PostingMode.APPROVAL.value
        assert post_job.status == PostJobStatus.RECEIVED.value
        assert media_asset.id is not None
        assert media_asset.post_job_id == post_job.id
        assert media_asset.status == MediaAssetStatus.RECEIVED.value

    with session_scope(session_factory) as session:
        repository = Repository(session)
        saved_job = repository.get_post_job(1)
        saved_asset = repository.get_media_asset(1)

        assert saved_job is not None
        assert saved_job.source_type == "telegram"
        assert saved_asset is not None
        assert saved_asset.mime_type == "image/jpeg"
