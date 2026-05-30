import asyncio
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import select

from app.config.settings import Settings
from app.db.models import PostJob
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.inputs.telegram_input import TelegramInput
from app.services.caption_service import CaptionPayload
from app.storage.local_storage import LocalStorage


class FakeTelegramFile:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self.content)


class FakeBot:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.get_file_calls: list[str] = []
        self.messages: list[tuple[str, str, object | None]] = []

    async def get_file(self, file_id: str) -> FakeTelegramFile:
        self.get_file_calls.append(file_id)
        return FakeTelegramFile(self.content)

    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        self.messages.append((chat_id, text, reply_markup))


class FakeCaptionGenerator:
    def generate(self, post_job: PostJob) -> CaptionPayload:
        return CaptionPayload(
            caption="テスト投稿です",
            hashtags=["#test"],
            alt_text="青い画像のテストです",
            warnings=[],
            should_post=True,
        )


def test_telegram_caption_genre_is_saved(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    telegram_input = TelegramInput(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        caption_generator=FakeCaptionGenerator(),
    )
    bot = FakeBot(content=_image_bytes(tmp_path / "genre.jpg"))

    asyncio.run(telegram_input.handle_media(_photo_update(caption="g=2,3"), SimpleNamespace(bot=bot)))

    with session_scope(session_factory) as session:
        post_job = session.scalars(select(PostJob)).one()

    assert post_job.genre_key == "slot_result,slot_moment"
    assert post_job.genre_label == "実戦結果 / 出目・演出"
    assert post_job.caption_instruction
    assert "slot_result" in post_job.caption_instruction


def test_telegram_caption_unknown_genre_stops_before_download(tmp_path: Path):
    settings, session_factory, storage = _build_context(tmp_path)
    telegram_input = TelegramInput(
        settings=settings,
        session_factory=session_factory,
        storage=storage,
        caption_generator=FakeCaptionGenerator(),
    )
    bot = FakeBot(content=_image_bytes(tmp_path / "unknown.jpg"))

    asyncio.run(telegram_input.handle_media(_photo_update(caption="abc"), SimpleNamespace(bot=bot)))

    with session_scope(session_factory) as session:
        post_jobs = session.scalars(select(PostJob)).all()

    assert post_jobs == []
    assert bot.get_file_calls == []
    assert "不明なジャンルです: abc" in bot.messages[0][1]
    assert "1 = slot_daily / 稼働日記" in bot.messages[0][1]


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        telegram_allowed_chat_ids=["12345"],
    )
    engine = create_app_engine(settings)
    init_db(engine)
    session_factory = create_session_factory(engine)
    return settings, session_factory, LocalStorage(settings=settings)


def _photo_update(*, caption: str | None):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=12345),
        effective_user=SimpleNamespace(id=67890),
        message=SimpleNamespace(
            photo=[SimpleNamespace(file_id="photo-file-id", file_unique_id="photo-unique")],
            video=None,
            document=None,
            caption=caption,
        ),
    )


def _image_bytes(path: Path) -> bytes:
    image = Image.new("RGB", (320, 240), (40, 90, 160))
    image.save(path, format="JPEG")
    return path.read_bytes()
