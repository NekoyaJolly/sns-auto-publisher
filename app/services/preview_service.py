from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import PostJob, PostJobStatus
from app.db.repository import Repository
from app.services.caption_service import CaptionGenerator, CaptionService
from app.services.publish_service import Publisher, PublishService


class PreviewAction(StrEnum):
    APPROVE = "approve"
    REGENERATE = "regenerate"
    REJECT = "reject"


class PreviewMessenger(Protocol):
    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        pass


@dataclass(frozen=True)
class PreviewCallback:
    action: PreviewAction
    post_job_id: int


class PreviewService:
    callback_prefix = "post"

    def __init__(
        self,
        session: Session,
        settings: Settings,
        messenger: PreviewMessenger,
        caption_generator: CaptionGenerator | None = None,
        publisher: Publisher | None = None,
    ) -> None:
        self.repository = Repository(session)
        self.settings = settings
        self.messenger = messenger
        self.caption_generator = caption_generator
        self.publisher = publisher

    async def send_preview(self, chat_id: str, post_job: PostJob) -> None:
        if post_job.status != PostJobStatus.CAPTIONED.value:
            raise ValueError("プレビュー送信はcaptioned状態のpost_jobのみ実行できます")

        self.repository.update_post_job_status(post_job, PostJobStatus.PREVIEW_SENT)
        await self.messenger.send_message(
            chat_id=chat_id,
            text=build_preview_text(post_job),
            reply_markup=build_preview_keyboard(post_job.id),
        )
        self.repository.update_post_job_status(post_job, PostJobStatus.WAITING_APPROVAL)

    async def handle_callback(self, chat_id: str, callback_data: str) -> PostJob:
        callback = parse_preview_callback(callback_data)
        post_job = self.repository.require_post_job(callback.post_job_id)

        if callback.action == PreviewAction.APPROVE:
            return await self._approve(chat_id, post_job)
        if callback.action == PreviewAction.REGENERATE:
            return await self._regenerate(chat_id, post_job)
        return await self._reject(chat_id, post_job)

    async def _approve(self, chat_id: str, post_job: PostJob) -> PostJob:
        if post_job.status != PostJobStatus.WAITING_APPROVAL.value:
            raise ValueError("承認できるpost_job状態ではありません")
        updated = self.repository.update_post_job_status(post_job, PostJobStatus.PUBLISHING)
        result = PublishService(
            session=self.repository.session,
            settings=self.settings,
            publisher=self.publisher,
        ).publish_post_job(updated)
        if result.is_success:
            await self.messenger.send_message(chat_id=chat_id, text=f"投稿完了しました。job_id={post_job.id} / x_post_id={result.x_post_id}")
        else:
            await self.messenger.send_message(chat_id=chat_id, text=f"投稿に失敗しました。job_id={post_job.id} / reason={result.error_message}")
        return updated

    async def _regenerate(self, chat_id: str, post_job: PostJob) -> PostJob:
        if post_job.status != PostJobStatus.WAITING_APPROVAL.value:
            raise ValueError("再生成できるpost_job状態ではありません")
        captioned = CaptionService(
            session=self.repository.session,
            settings=self.settings,
            generator=self.caption_generator,
        ).caption_post_job(post_job)
        if captioned.status != PostJobStatus.CAPTIONED.value:
            await self.messenger.send_message(chat_id=chat_id, text=captioned.error_message or "再生成に失敗しました")
            return captioned
        await self.send_preview(chat_id, captioned)
        return captioned

    async def _reject(self, chat_id: str, post_job: PostJob) -> PostJob:
        if post_job.status != PostJobStatus.WAITING_APPROVAL.value:
            raise ValueError("却下できるpost_job状態ではありません")
        updated = self.repository.update_post_job_status(
            post_job,
            PostJobStatus.REJECTED,
            error_message="Telegramで却下されました",
        )
        await self.messenger.send_message(chat_id=chat_id, text=f"投稿を却下しました。job_id={post_job.id}")
        return updated


def build_preview_text(post_job: PostJob) -> str:
    hashtags = json.loads(post_job.hashtags_json or "[]")
    warnings = json.loads(post_job.ai_warnings_json or "[]")
    lines = [
        f"投稿プレビュー job_id={post_job.id}",
        "",
        post_job.caption or "",
    ]
    if hashtags:
        lines.extend(["", " ".join(hashtags)])
    if post_job.alt_text:
        lines.extend(["", f"alt_text: {post_job.alt_text}"])
    if warnings:
        lines.extend(["", "warnings:", *[f"- {warning}" for warning in warnings]])
    return "\n".join(lines).strip()


def build_preview_keyboard(post_job_id: int):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("投稿する", callback_data=build_preview_callback(PreviewAction.APPROVE, post_job_id)),
                InlineKeyboardButton("再生成", callback_data=build_preview_callback(PreviewAction.REGENERATE, post_job_id)),
                InlineKeyboardButton("却下", callback_data=build_preview_callback(PreviewAction.REJECT, post_job_id)),
            ]
        ]
    )


def build_preview_callback(action: PreviewAction, post_job_id: int) -> str:
    return f"{PreviewService.callback_prefix}:{action.value}:{post_job_id}"


def parse_preview_callback(callback_data: str) -> PreviewCallback:
    try:
        prefix, action, post_job_id = callback_data.split(":", maxsplit=2)
        if prefix != PreviewService.callback_prefix:
            raise ValueError
        return PreviewCallback(action=PreviewAction(action), post_job_id=int(post_job_id))
    except (ValueError, TypeError) as exc:
        raise ValueError("不正なプレビューcallback dataです") from exc
