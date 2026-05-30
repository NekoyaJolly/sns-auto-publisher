from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TelegramMessenger(Protocol):
    async def send_message(self, chat_id: str, text: str) -> None:
        pass


@dataclass(frozen=True)
class ReceiveNotification:
    post_job_id: int
    media_count: int


class NotifyService:
    def __init__(self, messenger: TelegramMessenger) -> None:
        self.messenger = messenger

    async def notify_received(self, chat_id: str, notification: ReceiveNotification) -> None:
        text = f"受信しました。job_id={notification.post_job_id} / media={notification.media_count}"
        await self.messenger.send_message(chat_id=chat_id, text=text)

    async def notify_rejected(self, chat_id: str, reason: str) -> None:
        await self.messenger.send_message(chat_id=chat_id, text=f"受信できませんでした: {reason}")
