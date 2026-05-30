import asyncio
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import select

from app.config.settings import Settings
from app.db.models import MediaAsset, PostJob
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.inputs.telegram_input import TelegramInput
from app.storage.local_storage import LocalStorage


class FakeTelegramFile:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self.content)


class FakeBot:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.messages: list[tuple[str, str]] = []

    async def get_file(self, file_id: str) -> FakeTelegramFile:
        return FakeTelegramFile(self.content)

    async def send_message(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


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
    telegram_input = TelegramInput(settings=settings, session_factory=session_factory, storage=storage)
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
    assert bot.messages == [("12345", "受信しました。job_id=1 / media=1")]


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
