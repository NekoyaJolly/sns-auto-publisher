from __future__ import annotations

import logging
import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import MediaAsset, PostJob, PostJobStatus
from app.db.repository import Repository

logger = logging.getLogger(__name__)


class CaptionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caption: str = Field(min_length=1)
    hashtags: list[str] = Field(default_factory=list)
    alt_text: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)
    should_post: bool

    @field_validator("hashtags")
    @classmethod
    def normalize_hashtags(cls, hashtags: list[str]) -> list[str]:
        normalized: list[str] = []
        for hashtag in hashtags:
            stripped = hashtag.strip()
            if not stripped:
                continue
            normalized.append(stripped if stripped.startswith("#") else f"#{stripped}")
        return normalized


class CaptionGenerator(Protocol):
    def generate(self, post_job: PostJob) -> CaptionPayload:
        pass


@dataclass(frozen=True)
class CaptionPrompt:
    system: str
    user: str


class OpenAICaptionGenerator:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEYが設定されていません")
        if not settings.openai_model:
            raise ValueError("OPENAI_MODELが設定されていません")
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def generate(self, post_job: PostJob) -> CaptionPayload:
        prompt = build_caption_prompt(post_job)
        response = self.client.responses.create(
            model=self.settings.openai_model,
            input=build_caption_input(prompt, post_job),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "sns_caption_payload",
                    "strict": True,
                    "schema": caption_json_schema(),
                }
            },
        )
        return parse_caption_payload(str(response.output_text))


class CaptionService:
    allowed_statuses = {
        PostJobStatus.PROCESSED.value,
        PostJobStatus.CAPTIONED.value,
        PostJobStatus.PREVIEW_SENT.value,
        PostJobStatus.WAITING_APPROVAL.value,
    }

    def __init__(
        self,
        session: Session,
        settings: Settings,
        generator: CaptionGenerator | None = None,
    ) -> None:
        self.repository = Repository(session)
        self.settings = settings
        self.generator = generator

    def caption_post_job(self, post_job: PostJob) -> PostJob:
        if post_job.status not in self.allowed_statuses:
            raise ValueError("AI生成はprocessed/captioned/preview_sent/waiting_approval状態のpost_jobのみ実行できます")

        self.repository.update_post_job_status(post_job, PostJobStatus.CAPTIONING)
        try:
            generator = self.generator or OpenAICaptionGenerator(self.settings)
            payload = generator.generate(post_job)
        except Exception as exc:
            logger.exception("AI投稿文生成に失敗しました")
            return self.repository.update_post_job_status(
                post_job,
                PostJobStatus.FAILED,
                error_message=str(exc),
            )

        if not payload.should_post:
            return self.repository.update_post_job_caption(
                post_job,
                caption=payload.caption,
                hashtags=payload.hashtags,
                alt_text=payload.alt_text,
                ai_warnings=payload.warnings,
                status=PostJobStatus.REJECTED,
                error_message="AI判定により投稿しません",
            )

        return self.repository.update_post_job_caption(
            post_job,
            caption=payload.caption,
            hashtags=payload.hashtags,
            alt_text=payload.alt_text,
            ai_warnings=payload.warnings,
            status=PostJobStatus.CAPTIONED,
        )


def parse_caption_payload(raw_json: str) -> CaptionPayload:
    try:
        return CaptionPayload.model_validate_json(raw_json)
    except ValidationError as exc:
        raise ValueError("AI出力JSONの形式が不正です") from exc


def caption_json_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["caption", "hashtags", "alt_text", "warnings", "should_post"],
        "properties": {
            "caption": {"type": "string", "minLength": 1},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "alt_text": {"type": "string", "minLength": 1},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "should_post": {"type": "boolean"},
        },
    }


def build_caption_prompt(post_job: PostJob) -> CaptionPrompt:
    media_lines = "\n".join(_media_summary(media_asset) for media_asset in post_job.media_assets)
    system = (
        "あなたはSNS投稿文を作る編集者です。"
        "出力は必ず指定JSON Schemaに従い、caption、hashtags、alt_text、warnings、should_postを返してください。"
        "captionは日本語で自然に、hashtagsは少数に絞り、alt_textはアクセシビリティ向けに具体的にしてください。"
        "添付された画像または動画サムネイルを必ず観察し、見えていない内容を推測で書かないでください。"
    )
    user = (
        "以下の処理済みメディア情報と添付画像からX投稿用のJSONを生成してください。\n"
        f"投稿モード: {post_job.mode}\n"
        f"メディア:\n{media_lines}\n"
        "動画の場合はサムネイル画像を添付しています。\n"
        "重大な懸念がある場合はwarningsに理由を書き、should_post=falseにしてください。"
    )
    return CaptionPrompt(system=system, user=user)


def build_caption_input(prompt: CaptionPrompt, post_job: PostJob) -> list[dict[str, object]]:
    content: list[dict[str, object]] = [{"type": "input_text", "text": prompt.user}]
    content.extend(_media_image_parts(post_job.media_assets))
    if len(content) == 1:
        raise ValueError("AI生成に必要な画像または動画サムネイルが見つかりません")
    return [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": content},
    ]


def _media_summary(media_asset: MediaAsset) -> str:
    parts = [
        f"id={media_asset.id}",
        f"type={media_asset.media_type}",
        f"mime={media_asset.mime_type}",
        f"processed_path={media_asset.processed_path}",
    ]
    if media_asset.width and media_asset.height:
        parts.append(f"size={media_asset.width}x{media_asset.height}")
    if media_asset.duration_seconds is not None:
        parts.append(f"duration_seconds={media_asset.duration_seconds}")
    return "- " + ", ".join(parts)


def _media_image_parts(media_assets: list[MediaAsset]) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = []
    for media_asset in media_assets:
        path = _caption_visual_path(media_asset)
        if path is None:
            continue
        parts.append(
            {
                "type": "input_image",
                "image_url": _data_url(path),
            }
        )
    return parts


def _caption_visual_path(media_asset: MediaAsset) -> Path | None:
    if media_asset.media_type == "image" and media_asset.processed_path:
        path = Path(media_asset.processed_path)
    elif media_asset.media_type == "video" and media_asset.thumbnail_path:
        path = Path(media_asset.thumbnail_path)
    else:
        return None
    return path if path.exists() else None


def _data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
