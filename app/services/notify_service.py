from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TelegramMessenger(Protocol):
    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        pass


@dataclass(frozen=True)
class ReceiveNotification:
    post_job_id: int
    media_count: int
    detail: str | None = None


class NotifyService:
    def __init__(self, messenger: TelegramMessenger) -> None:
        self.messenger = messenger

    async def notify_received(self, chat_id: str, notification: ReceiveNotification) -> None:
        text = f"受信しました。job_id={notification.post_job_id} / media={notification.media_count}"
        if notification.detail:
            text = f"{text} / {notification.detail}"
        await self.messenger.send_message(chat_id=chat_id, text=text)

    async def notify_rejected(self, chat_id: str, reason: str) -> None:
        await self.messenger.send_message(chat_id=chat_id, text=f"受信できませんでした: {reason}")

    async def notify_published(self, chat_id: str, *, post_job_id: int, x_post_id: str | None) -> None:
        x_post = x_post_id or "unknown"
        await self.messenger.send_message(chat_id=chat_id, text=f"投稿完了しました。job_id={post_job_id} / x_post_id={x_post}")

    async def notify_failed(self, chat_id: str, *, post_job_id: int, reason: str | None) -> None:
        message = reason or "理由不明のエラーです"
        await self.messenger.send_message(chat_id=chat_id, text=f"投稿に失敗しました。job_id={post_job_id} / reason={message}")
