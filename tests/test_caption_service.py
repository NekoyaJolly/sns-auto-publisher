import json
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.caption_service import (
    CaptionPayload,
    CaptionService,
    build_caption_input,
    build_caption_prompt,
    parse_caption_payload,
)


class FakeCaptionGenerator:
    def __init__(self, payload: CaptionPayload | None = None, exc: Exception | None = None) -> None:
        self.payload = payload or CaptionPayload(
            caption="朝の散歩で見つけた景色です。",
            hashtags=["morning", "#photo"],
            alt_text="朝の光が差し込む風景写真です。",
            warnings=[],
            should_post=True,
        )
        self.exc = exc

    def generate(self, post_job):
        if self.exc:
            raise self.exc
        return self.payload


def test_parse_caption_payload_normalizes_hashtags():
    payload = parse_caption_payload(
        json.dumps(
            {
                "caption": "投稿本文",
                "hashtags": ["tag", "#already"],
                "alt_text": "代替テキスト",
                "warnings": [],
                "should_post": True,
            }
        )
    )

    assert payload.hashtags == ["#tag", "#already"]


def test_caption_service_stores_ai_output(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session)

        CaptionService(
            session=session,
            settings=settings,
            generator=FakeCaptionGenerator(),
        ).caption_post_job(post_job)

        assert post_job.status == PostJobStatus.CAPTIONED.value
        assert post_job.caption == "朝の散歩で見つけた景色です。"
        assert json.loads(post_job.hashtags_json or "[]") == ["#morning", "#photo"]
        assert post_job.alt_text == "朝の光が差し込む風景写真です。"
        assert json.loads(post_job.ai_warnings_json or "[]") == []


def test_caption_service_rejects_when_should_post_is_false(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    payload = CaptionPayload(
        caption="投稿は控えます。",
        hashtags=[],
        alt_text="判定対象のメディアです。",
        warnings=["公開に適さない可能性があります"],
        should_post=False,
    )

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session)

        CaptionService(
            session=session,
            settings=settings,
            generator=FakeCaptionGenerator(payload=payload),
        ).caption_post_job(post_job)

        assert post_job.status == PostJobStatus.REJECTED.value
        assert post_job.error_message == "AI判定により投稿しません"
        assert json.loads(post_job.ai_warnings_json or "[]") == ["公開に適さない可能性があります"]


def test_caption_service_marks_invalid_json_as_failed(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session)

        CaptionService(
            session=session,
            settings=settings,
            generator=FakeCaptionGenerator(exc=ValueError("AI出力JSONの形式が不正です")),
        ).caption_post_job(post_job)

        assert post_job.status == PostJobStatus.FAILED.value
        assert "AI出力JSON" in (post_job.error_message or "")


def test_caption_service_requires_processed_post_job(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        repository = Repository(session)
        post_job = repository.create_post_job(source_type="telegram")

        with pytest.raises(ValueError, match="processed"):
            CaptionService(
                session=session,
                settings=settings,
                generator=FakeCaptionGenerator(),
            ).caption_post_job(post_job)


def test_build_caption_input_includes_processed_image_bytes(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    image_path = tmp_path / "processed.jpg"
    image_path.write_bytes(b"fake image bytes")

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session, processed_path=str(image_path))
        prompt = build_caption_prompt(post_job)

        request_input = build_caption_input(prompt, post_job)

    user_content = request_input[1]["content"]
    assert isinstance(user_content, list)
    image_part = user_content[1]
    assert image_part["type"] == "input_image"
    assert str(image_part["image_url"]).startswith("data:image/jpeg;base64,")


def test_build_caption_input_uses_video_thumbnail(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)
    thumbnail_path = tmp_path / "thumbnail.jpg"
    thumbnail_path.write_bytes(b"fake thumbnail bytes")

    with session_scope(session_factory) as session:
        repository = Repository(session)
        post_job = repository.create_post_job(source_type="telegram")
        media_asset = repository.create_media_asset(
            post_job_id=post_job.id,
            original_path="storage/raw/1/movie.mov",
            processed_path="storage/processed/1/movie.mp4",
            thumbnail_path=str(thumbnail_path),
            media_type="video",
            mime_type="video/quicktime",
            file_hash="hash",
            file_size=123,
            width=640,
            height=480,
            duration_seconds=5.0,
            status=MediaAssetStatus.PROCESSED,
        )
        post_job.media_assets.append(media_asset)
        repository.update_post_job_status_from_media_assets(post_job)
        prompt = build_caption_prompt(post_job)

        request_input = build_caption_input(prompt, post_job)

    user_content = request_input[1]["content"]
    assert isinstance(user_content, list)
    assert user_content[1]["type"] == "input_image"


def test_build_caption_input_requires_visual_file(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session, processed_path=str(tmp_path / "missing.jpg"))
        prompt = build_caption_prompt(post_job)

        with pytest.raises(ValueError, match="画像または動画サムネイル"):
            build_caption_input(prompt, post_job)


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)


def _create_processed_post_job(session, *, processed_path: str = "storage/processed/1/photo.jpg"):
    repository = Repository(session)
    post_job = repository.create_post_job(source_type="telegram")
    media_asset = repository.create_media_asset(
        post_job_id=post_job.id,
        original_path="storage/raw/1/photo.jpg",
        processed_path=processed_path,
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
