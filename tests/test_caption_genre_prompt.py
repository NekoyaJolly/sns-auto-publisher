import json
from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJobStatus
from app.db.repository import Repository
from app.db.session import create_app_engine, create_session_factory, init_db, session_scope
from app.services.caption_service import CaptionPayload, CaptionService, build_caption_prompt


class ManyHashtagGenerator:
    def generate(self, post_job):
        return CaptionPayload(
            caption="短い投稿本文です。",
            hashtags=["#a", "#b", "#c", "#d", "#e"],
            alt_text="画像の説明です。",
            warnings=[],
            should_post=True,
        )


def test_caption_prompt_includes_genre_rules(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session, genre_key="slot_result,slot_moment")

        prompt = build_caption_prompt(post_job)

    assert "genre_key: slot_result,slot_moment" in prompt.user
    assert "genre_label: 実戦結果 / 出目・演出" in prompt.user
    assert "実戦結果を淡々と振り返る" in prompt.user
    assert "出目、演出、上乗せ、珍しい瞬間を共有する" in prompt.user
    assert "勝てる、稼げる、確実、鉄板、保証などの断定表現" in prompt.user
    assert "#実戦結果" in prompt.user
    assert "#演出" in prompt.user
    assert "ハッシュタグ候補は固定挿入ではなく" in prompt.user
    assert "max_hashtags: 4" in prompt.user


def test_caption_service_limits_hashtags_by_genre_rules(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session, genre_key="slot_daily")

        CaptionService(
            session=session,
            settings=settings,
            generator=ManyHashtagGenerator(),
        ).caption_post_job(post_job)

        assert post_job.status == PostJobStatus.CAPTIONED.value
        assert json.loads(post_job.hashtags_json or "[]") == ["#a", "#b", "#c"]


def test_caption_service_uses_larger_selected_genre_limit_capped_by_common_rules(tmp_path: Path):
    settings, session_factory = _build_context(tmp_path)

    with session_scope(session_factory) as session:
        post_job = _create_processed_post_job(session, genre_key="slot_daily,slot_moment")

        CaptionService(
            session=session,
            settings=settings,
            generator=ManyHashtagGenerator(),
        ).caption_post_job(post_job)

        assert json.loads(post_job.hashtags_json or "[]") == ["#a", "#b", "#c", "#d"]


def _build_context(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
    )
    engine = create_app_engine(settings)
    init_db(engine)
    return settings, create_session_factory(engine)


def _create_processed_post_job(session, *, genre_key: str):
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
    repository.update_post_job_genre(
        post_job,
        genre_key=genre_key,
        genre_label=None,
        caption_instruction=None,
    )
    return post_job
