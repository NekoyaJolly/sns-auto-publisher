import asyncio
from pathlib import Path

from PIL import Image

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJob, PostJobStatus
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.caption_service import CaptionPayload, CaptionService
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.media_process_service import MediaProcessService
from app.services.preview_service import PreviewService
from app.services.validation_service import ValidationService
from app.storage.local_storage import LocalStorage
from app.utils.ffmpeg_runner import VideoProbeInfo


class FakeCaptionGenerator:
    def generate(self, post_job: PostJob) -> CaptionPayload:
        return CaptionPayload(
            caption="MVP確認用の投稿です",
            hashtags=["#mvp"],
            alt_text="MVP確認用メディアの説明です",
            warnings=[],
            should_post=True,
        )


class FakeMessenger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, object | None]] = []

    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        self.messages.append((chat_id, text, reply_markup))


class FakeVideoRunner:
    def probe_video(self, input_path: Path) -> VideoProbeInfo:
        return VideoProbeInfo(
            duration_seconds=9.5,
            width=1280,
            height=720,
            codec_name="h264",
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
        )

    def convert_to_mp4(self, *, input_path: Path, output_path: Path, max_width: int, max_height: int) -> None:
        Path(output_path).write_bytes(b"processed video")

    def create_thumbnail(self, *, input_path: Path, output_path: Path, seek_seconds: float = 1.0) -> None:
        Path(output_path).write_bytes(b"thumbnail")


def test_mvp_image_normal_flow_reaches_approval_preview(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    messenger = FakeMessenger()

    with session_scope(session_factory) as session:
        result = IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
            chat_id="12345",
            user_id="67890",
            media_files=[
                IncomingMediaFile(
                    filename="photo.jpg",
                    content=_image_bytes(tmp_path / "source.jpg"),
                    media_type="image",
                    mime_type="image/jpeg",
                )
            ],
        )
        ValidationService(session=session, settings=settings).validate_post_job(result.post_job)
        MediaProcessService(session=session, storage=storage).process_post_job_media(result.post_job)
        CaptionService(
            session=session,
            settings=settings,
            generator=FakeCaptionGenerator(),
        ).caption_post_job(result.post_job)
        asyncio.run(PreviewService(session, settings, messenger).send_preview("12345", result.post_job))

        assert result.post_job.status == PostJobStatus.WAITING_APPROVAL.value
        assert result.media_assets[0].status == MediaAssetStatus.PROCESSED.value
        assert result.post_job.caption == "MVP確認用の投稿です"
        assert messenger.messages[0][1].startswith("投稿プレビュー job_id=")
        assert messenger.messages[0][2] is not None


def test_mvp_video_normal_flow_reaches_processed(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    runner = FakeVideoRunner()

    with session_scope(session_factory) as session:
        result = IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
            chat_id="12345",
            user_id="67890",
            media_files=[
                IncomingMediaFile(
                    filename="movie.mov",
                    content=b"raw video bytes",
                    media_type="video",
                    mime_type="video/quicktime",
                )
            ],
        )
        ValidationService(session=session, settings=settings, ffmpeg_runner=runner).validate_post_job(result.post_job)
        MediaProcessService(session=session, storage=storage, ffmpeg_runner=runner).process_post_job_media(result.post_job)
        media_asset = result.media_assets[0]

        assert result.post_job.status == PostJobStatus.PROCESSED.value
        assert media_asset.status == MediaAssetStatus.PROCESSED.value
        assert media_asset.duration_seconds == 9.5
        assert media_asset.width == 1280
        assert media_asset.height == 720
        assert media_asset.processed_path is not None
        assert media_asset.thumbnail_path is not None


def test_mvp_multiple_images_are_saved_and_processed(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        result = IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
            chat_id="12345",
            user_id="67890",
            media_files=[
                IncomingMediaFile(
                    filename="photo-1.jpg",
                    content=_image_bytes(tmp_path / "source-1.jpg"),
                    media_type="image",
                    mime_type="image/jpeg",
                ),
                IncomingMediaFile(
                    filename="photo-2.jpg",
                    content=_image_bytes(tmp_path / "source-2.jpg"),
                    media_type="image",
                    mime_type="image/jpeg",
                ),
            ],
        )
        ValidationService(session=session, settings=settings).validate_post_job(result.post_job)
        MediaProcessService(session=session, storage=storage).process_post_job_media(result.post_job)

        assert result.post_job.status == PostJobStatus.PROCESSED.value
        assert len(result.media_assets) == 2
        assert all(media_asset.status == MediaAssetStatus.PROCESSED.value for media_asset in result.media_assets)
        assert all(media_asset.processed_path is not None for media_asset in result.media_assets)


def test_mvp_rejected_and_failed_reasons_are_persisted(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        rejected = IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
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
        failed = IngestService(session=session, storage=storage, settings=settings).ingest_telegram_media(
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

        ValidationService(session=session, settings=settings).validate_post_job(rejected.post_job)
        ValidationService(session=session, settings=settings).validate_post_job(failed.post_job)

        assert rejected.post_job.status == PostJobStatus.REJECTED.value
        assert rejected.media_assets[0].status == MediaAssetStatus.REJECTED.value
        assert rejected.post_job.error_message
        assert failed.post_job.status == PostJobStatus.FAILED.value
        assert failed.media_assets[0].status == MediaAssetStatus.FAILED.value
        assert failed.post_job.error_message


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine), LocalStorage(settings=settings)


def _image_bytes(path: Path) -> bytes:
    image = Image.new("RGB", (640, 480), (80, 140, 200))
    image.save(path, format="JPEG")
    return path.read_bytes()
