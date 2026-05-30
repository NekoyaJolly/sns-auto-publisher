from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.media_process_service import MediaProcessService
from app.services.validation_service import ValidationService
from app.storage.local_storage import LocalStorage
from app.utils.ffmpeg_runner import FFmpegExecutionError, VideoProbeInfo


class FakeVideoRunner:
    def __init__(self, *, convert_error: Exception | None = None) -> None:
        self.convert_error = convert_error
        self.convert_calls: list[tuple[Path, Path]] = []
        self.thumbnail_calls: list[tuple[Path, Path]] = []

    def probe_video(self, input_path: Path) -> VideoProbeInfo:
        return VideoProbeInfo(
            duration_seconds=8.25,
            width=960,
            height=540,
            codec_name="h264",
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
        )

    def convert_to_mp4(self, *, input_path: Path, output_path: Path, max_width: int, max_height: int) -> None:
        if self.convert_error:
            raise self.convert_error
        self.convert_calls.append((Path(input_path), Path(output_path)))
        Path(output_path).write_bytes(b"processed video")

    def create_thumbnail(self, *, input_path: Path, output_path: Path, seek_seconds: float = 1.0) -> None:
        self.thumbnail_calls.append((Path(input_path), Path(output_path)))
        Path(output_path).write_bytes(b"thumbnail")


def test_video_process_service_saves_processed_video_and_thumbnail(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    runner = FakeVideoRunner()

    with session_scope(session_factory) as session:
        result = _ingest_and_validate_video(session, settings, storage, runner)
        raw_path = Path(result.media_assets[0].original_path)
        raw_before = raw_path.read_bytes()

        processed_assets = MediaProcessService(
            session=session,
            storage=storage,
            ffmpeg_runner=runner,
        ).process_post_job_media(result.post_job)
        media_asset = processed_assets[0]

        assert result.post_job.status == PostJobStatus.PROCESSED.value
        assert media_asset.status == MediaAssetStatus.PROCESSED.value
        assert media_asset.processed_path is not None
        assert media_asset.thumbnail_path is not None
        assert media_asset.duration_seconds == 8.25
        assert media_asset.width == 960
        assert media_asset.height == 540

    assert raw_path.read_bytes() == raw_before
    assert Path(media_asset.processed_path).exists()
    assert Path(media_asset.thumbnail_path).exists()
    assert Path(media_asset.processed_path).read_bytes() == b"processed video"
    assert Path(media_asset.thumbnail_path).read_bytes() == b"thumbnail"
    assert runner.convert_calls[0][0] == raw_path


def test_video_process_service_marks_ffmpeg_failure_as_failed(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    runner = FakeVideoRunner(convert_error=FFmpegExecutionError("ffmpegによる動画変換に失敗しました"))

    with session_scope(session_factory) as session:
        result = _ingest_and_validate_video(session, settings, storage, runner)

        processed_assets = MediaProcessService(
            session=session,
            storage=storage,
            ffmpeg_runner=runner,
        ).process_post_job_media(result.post_job)
        media_asset = processed_assets[0]

        assert media_asset.status == MediaAssetStatus.FAILED.value
        assert "動画変換" in (media_asset.error_message or "")
        assert result.post_job.status == PostJobStatus.FAILED.value


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


def _ingest_and_validate_video(session, settings: Settings, storage: LocalStorage, runner: FakeVideoRunner):
    result = IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
        chat_id="12345",
        user_id="67890",
        media_files=[
            IncomingMediaFile(
                filename="movie.mov",
                content=b"raw video",
                media_type="video",
                mime_type="video/quicktime",
            )
        ],
    )
    ValidationService(session=session, settings=settings, ffmpeg_runner=runner).validate_post_job(result.post_job)
    return result
