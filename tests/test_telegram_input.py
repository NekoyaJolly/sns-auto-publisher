import asyncio
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import select

from app.config.settings import Settings
from app.db.models import MediaAsset, MediaAssetStatus, PostJob, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.inputs.telegram_input import TelegramInput
from app.services.caption_service import CaptionPayload
from app.services.preview_service import PreviewAction, build_preview_callback
from app.storage.local_storage import LocalStorage


class FakeTelegramFile:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self.content)


class FakeBot:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.messages: list[tuple[str, str, object | None]] = []

    async def get_file(self, file_id: str) -> FakeTelegramFile:
        return FakeTelegramFile(self.content)

    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        self.messages.append((chat_id, text, reply_markup))


class FakeCallbackQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


def test_telegram_input_extracts_photo_candidate(tmp_path: Path):
    telegram_input = _build_telegram_input(tmp_path)
    update = SimpleNamespace(
        message=SimpleNamespace(
            photo=[
                SimpleNamespace(file_id="small", file_unique_id="small-unique"),
                SimpleNamespace(file_id="large", file_unique_id="large-unique"),
            ],
            video=None,
            document=None,
        )
    )

    candidate = telegram_input.extract_media_candidate(update)

    assert candidate is not None
    assert candidate.file_id == "large"
    assert candidate.filename == "large-unique.jpg"
    assert candidate.media_type == "image"


def test_telegram_input_rejects_unallowed_chat(tmp_path: Path):
    telegram_input = _build_telegram_input(tmp_path, allowed_chat_ids=["12345"])

    assert telegram_input.is_allowed_chat("12345") is True
    assert telegram_input.is_allowed_chat("99999") is False


def test_telegram_input_handles_photo_and_creates_raw_records(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        telegram_allowed_chat_ids=["12345"],
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    storage = LocalStorage(settings=settings)
    telegram_input = TelegramInput(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        caption_generator=FakeCaptionGenerator(),
    )
    bot = FakeBot(content=_image_bytes(tmp_path / "telegram.jpg"))
    context = SimpleNamespace(bot=bot)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_user=SimpleNamespace(id=67890),
        message=SimpleNamespace(
            photo=[SimpleNamespace(file_id="photo-file-id", file_unique_id="photo-unique")],
            video=None,
            document=None,
        ),
    )

    asyncio.run(telegram_input.handle_media(update, context))

    with session_scope(session_factory) as session:
        post_jobs = session.scalars(select(PostJob)).all()
        media_assets = session.scalars(select(MediaAsset)).all()

    assert len(post_jobs) == 1
    assert post_jobs[0].source_chat_id == "12345"
    assert len(media_assets) == 1
    assert Path(media_assets[0].original_path).exists()
    assert Path(media_assets[0].processed_path).exists()
    assert Path(media_assets[0].thumbnail_path).exists()
    assert media_assets[0].media_type == "image"
    assert post_jobs[0].status == "waiting_approval"
    assert len(bot.messages) == 2
    assert bot.messages[0][0] == "12345"
    assert bot.messages[0][1].startswith("投稿プレビュー job_id=1")
    assert bot.messages[0][2] is not None
    assert bot.messages[1] == ("12345", "受信しました。job_id=1 / media=1 / AI生成完了 / プレビュー送信完了", None)


def test_telegram_input_handles_approve_callback(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        telegram_allowed_chat_ids=["12345"],
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        post_job = _create_waiting_post_job(session)
        post_job_id = post_job.id

    telegram_input = TelegramInput(
        settings=settings,
        session_factory=session_factory,
        storage=LocalStorage(settings=settings),
        caption_generator=FakeCaptionGenerator(),
    )
    bot = FakeBot(content=b"")
    callback_query = FakeCallbackQuery(build_preview_callback(PreviewAction.APPROVE, post_job_id))
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_user=SimpleNamespace(id=67890),
        callback_query=callback_query,
    )

    asyncio.run(telegram_input.handle_preview_callback(update, SimpleNamespace(bot=bot)))

    with session_scope(session_factory) as session:
        saved_job = Repository(session).require_post_job(post_job_id)

    assert callback_query.answered is True
    assert saved_job.status == PostJobStatus.PUBLISHING.value
    assert bot.messages == [("12345", f"投稿処理へ進みます。job_id={post_job_id}", None)]


def _build_telegram_input(tmp_path: Path, allowed_chat_ids: list[str] | None = None) -> TelegramInput:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        telegram_allowed_chat_ids=allowed_chat_ids or [],
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    return TelegramInput(settings=settings, session_factory=session_factory, storage=LocalStorage(settings=settings))


def _image_bytes(path: Path) -> bytes:
    image = Image.new("RGB", (320, 240), (40, 90, 160))
    image.save(path, format="JPEG")
    return path.read_bytes()


class FakeCaptionGenerator:
    def generate(self, post_job: PostJob) -> CaptionPayload:
        return CaptionPayload(
            caption="テスト投稿です",
            hashtags=["#test"],
            alt_text="青い画像のテストです",
            warnings=[],
            should_post=True,
        )


def _create_waiting_post_job(session):
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
    repository.update_post_job_status_from_media_assets(post_job)
    repository.update_post_job_caption(
        post_job,
        caption="投稿本文です",
        hashtags=["#test"],
        alt_text="代替テキストです",
        ai_warnings=[],
        status=PostJobStatus.CAPTIONED,
    )
    return repository.update_post_job_status(post_job, PostJobStatus.WAITING_APPROVAL)
