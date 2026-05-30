from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.validation_service import ValidationService
from app.storage.local_storage import LocalStorage
from app.utils.ffmpeg_runner import FFmpegExecutionError, VideoProbeInfo


class FakeProbeRunner:
    def __init__(self, info: VideoProbeInfo | None = None, exc: Exception | None = None) -> None:
        self.info = info or VideoProbeInfo(
            duration_seconds=12.5,
            width=1280,
            height=720,
            codec_name="h264",
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
        )
        self.exc = exc

    def probe_video(self, input_path: Path) -> VideoProbeInfo:
        if self.exc:
            raise self.exc
        return self.info


def test_video_validation_allows_mp4_and_mov_mime(tmp_path: Path):
    for filename, mime_type in [("movie.mp4", "video/mp4"), ("movie.mov", "video/quicktime")]:
        settings, session_factory, storage = _build_context(tmp_path / filename)
        with session_scope(session_factory) as session:
            result = _ingest_video(session, settings, storage, filename=filename, mime_type=mime_type)
            validation = ValidationService(session=session, settings=settings, ffmpeg_runner=FakeProbeRunner())

            validation_results = validation.validate_post_job(result.post_job)

            assert validation_results[0].is_valid is True
            assert result.media_assets[0].status == MediaAssetStatus.VALIDATED.value
            assert result.media_assets[0].duration_seconds == 12.5
            assert result.media_assets[0].width == 1280
            assert result.media_assets[0].height == 720
            assert result.post_job.status == PostJobStatus.VALIDATED.value


def test_video_validation_rejects_non_video_mime(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    with session_scope(session_factory) as session:
        result = _ingest_video(session, settings, storage, filename="note.txt", mime_type="text/plain")
        validation = ValidationService(session=session, settings=settings, ffmpeg_runner=FakeProbeRunner())

        validation_results = validation.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.media_assets[0].status == MediaAssetStatus.REJECTED.value
        assert result.post_job.status == PostJobStatus.REJECTED.value


def test_video_validation_rejects_unsupported_extension(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    with session_scope(session_factory) as session:
        result = _ingest_video(session, settings, storage, filename="movie.avi", mime_type="video/mp4")
        validation = ValidationService(session=session, settings=settings, ffmpeg_runner=FakeProbeRunner())

        validation_results = validation.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.media_assets[0].status == MediaAssetStatus.REJECTED.value
        assert "拡張子" in (result.media_assets[0].error_message or "")


def test_video_validation_rejects_oversized_file(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path, max_video_size_mb=1)
    with session_scope(session_factory) as session:
        result = _ingest_video(
            session,
            settings,
            storage,
            filename="movie.mp4",
            mime_type="video/mp4",
            content=b"0" * (1024 * 1024 + 1),
        )
        validation = ValidationService(session=session, settings=settings, ffmpeg_runner=FakeProbeRunner())

        validation_results = validation.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.media_assets[0].status == MediaAssetStatus.REJECTED.value
        assert "ファイルサイズ" in (result.media_assets[0].error_message or "")


def test_video_validation_rejects_duration_limit(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path, max_video_duration_seconds=10)
    runner = FakeProbeRunner(info=VideoProbeInfo(12.0, 1280, 720, "h264", "mov,mp4"))
    with session_scope(session_factory) as session:
        result = _ingest_video(session, settings, storage, filename="movie.mp4", mime_type="video/mp4")
        validation = ValidationService(session=session, settings=settings, ffmpeg_runner=runner)

        validation_results = validation.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.media_assets[0].status == MediaAssetStatus.REJECTED.value
        assert "動画秒数" in (result.media_assets[0].error_message or "")


def test_video_validation_marks_ffprobe_failure_as_failed(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    runner = FakeProbeRunner(exc=FFmpegExecutionError("ffprobeによる動画メタデータ取得に失敗しました"))
    with session_scope(session_factory) as session:
        result = _ingest_video(session, settings, storage, filename="movie.mp4", mime_type="video/mp4")
        validation = ValidationService(session=session, settings=settings, ffmpeg_runner=runner)

        validation_results = validation.validate_post_job(result.post_job)

        assert validation_results[0].is_valid is False
        assert result.media_assets[0].status == MediaAssetStatus.FAILED.value
        assert result.post_job.status == PostJobStatus.FAILED.value


def _build_context(
    tmp_path: Path,
    *,
    max_video_size_mb: int = 512,
    max_video_duration_seconds: int = 140,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        max_video_size_mb=max_video_size_mb,
        max_video_duration_seconds=max_video_duration_seconds,
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    storage = LocalStorage(settings=settings)
    return settings, session_factory, storage


def _ingest_video(
    session,
    settings: Settings,
    storage: LocalStorage,
    *,
    filename: str,
    mime_type: str,
    content: bytes = b"video bytes",
):
    return IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
        chat_id="12345",
        user_id="67890",
        media_files=[
            IncomingMediaFile(
                filename=filename,
                content=content,
                media_type="video",
                mime_type=mime_type,
            )
        ],
    )
