from __future__ import annotations

import logging
from dataclasses import dataclass
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
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def generate(self, post_job: PostJob) -> CaptionPayload:
        prompt = build_caption_prompt(post_job)
        response = self.client.responses.create(
            model=self.settings.openai_model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
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
        if post_job.status != PostJobStatus.PROCESSED.value:
            raise ValueError("AI生成はprocessed状態のpost_jobのみ実行できます")

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
    )
    user = (
        "以下の処理済みメディア情報からX投稿用のJSONを生成してください。\n"
        f"投稿モード: {post_job.mode}\n"
        f"メディア:\n{media_lines}\n"
        "重大な懸念がある場合はwarningsに理由を書き、should_post=falseにしてください。"
    )
    return CaptionPrompt(system=system, user=user)


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
