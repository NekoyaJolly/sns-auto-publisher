import asyncio
import json
from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.caption_service import CaptionPayload
from app.services.preview_service import (
    PreviewAction,
    PreviewService,
    build_preview_callback,
    build_preview_text,
    parse_preview_callback,
)
from app.publishers.x_publisher import XPublishResult


class FakePreviewMessenger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, object | None]] = []

    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        self.messages.append((chat_id, text, reply_markup))


class FakeCaptionGenerator:
    def __init__(self) -> None:
        self.count = 0

    def generate(self, post_job):
        self.count += 1
        return CaptionPayload(
            caption=f"再生成された投稿文 {self.count}",
            hashtags=["#regen"],
            alt_text="再生成された代替テキストです。",
            warnings=[],
            should_post=True,
        )


class FakePublisher:
    def __init__(self, *, exc: Exception | None = None) -> None:
        self.exc = exc

    def publish(self, post_job):
        if self.exc:
            raise self.exc
        return XPublishResult(x_post_id="x-123", media_ids=["media-1"])


def test_preview_text_contains_caption_hashtags_alt_text_and_warnings(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_captioned_post_job(session)

        text = build_preview_text(post_job)

        assert "投稿プレビュー job_id=" in text
        assert "投稿本文です" in text
        assert "#photo #daily" in text
        assert "alt_text: 代替テキストです" in text
        assert "軽微な警告" in text


def test_send_preview_sets_waiting_approval_and_sends_buttons(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    messenger = FakePreviewMessenger()

    with session_scope(session_factory) as session:
        post_job = _create_captioned_post_job(session)

        asyncio.run(PreviewService(session, settings, messenger).send_preview("12345", post_job))

        assert post_job.status == PostJobStatus.WAITING_APPROVAL.value
        assert len(messenger.messages) == 1
        assert messenger.messages[0][0] == "12345"
        assert messenger.messages[0][1].startswith("投稿プレビュー")
        assert messenger.messages[0][2] is not None


def test_approve_callback_sets_publishing(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    messenger = FakePreviewMessenger()

    with session_scope(session_factory) as session:
        post_job = _create_waiting_post_job(session)
        callback_data = build_preview_callback(PreviewAction.APPROVE, post_job.id)

        updated = asyncio.run(
            PreviewService(
                session,
                settings,
                messenger,
                publisher=FakePublisher(),
            ).handle_callback("12345", callback_data)
        )

        assert updated.status == PostJobStatus.PUBLISHED.value
        assert updated.x_post_id == "x-123"
        assert messenger.messages[-1] == ("12345", f"投稿完了しました。job_id={post_job.id} / x_post_id=x-123", None)


def test_reject_callback_sets_rejected(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    messenger = FakePreviewMessenger()

    with session_scope(session_factory) as session:
        post_job = _create_waiting_post_job(session)
        callback_data = build_preview_callback(PreviewAction.REJECT, post_job.id)

        updated = asyncio.run(PreviewService(session, settings, messenger).handle_callback("12345", callback_data))

        assert updated.status == PostJobStatus.REJECTED.value
        assert updated.error_message == "Telegramで却下されました"
        assert messenger.messages[-1] == ("12345", f"投稿を却下しました。job_id={post_job.id}", None)


def test_regenerate_callback_reruns_caption_and_sends_new_preview(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    messenger = FakePreviewMessenger()
    generator = FakeCaptionGenerator()

    with session_scope(session_factory) as session:
        post_job = _create_waiting_post_job(session)
        callback_data = build_preview_callback(PreviewAction.REGENERATE, post_job.id)

        updated = asyncio.run(
            PreviewService(
                session,
                settings,
                messenger,
                caption_generator=generator,
            ).handle_callback("12345", callback_data)
        )

        assert updated.status == PostJobStatus.WAITING_APPROVAL.value
        assert updated.caption == "再生成された投稿文 1"
        assert json.loads(updated.hashtags_json or "[]") == ["#regen"]
        assert len(messenger.messages) == 1
        assert "再生成された投稿文 1" in messenger.messages[0][1]


def test_parse_preview_callback_rejects_invalid_data():
    try:
        parse_preview_callback("invalid")
    except ValueError as exc:
        assert "callback" in str(exc)
    else:
        raise AssertionError("不正なcallback dataはValueErrorにする必要があります")


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)


def _create_captioned_post_job(session):
    post_job = _create_processed_post_job(session)
    repository = Repository(session)
    return repository.update_post_job_caption(
        post_job,
        caption="投稿本文です",
        hashtags=["#photo", "#daily"],
        alt_text="代替テキストです",
        ai_warnings=["軽微な警告"],
        status=PostJobStatus.CAPTIONED,
    )


def _create_waiting_post_job(session):
    post_job = _create_captioned_post_job(session)
    return Repository(session).update_post_job_status(post_job, PostJobStatus.WAITING_APPROVAL)


def _create_processed_post_job(session):
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
    return post_job
