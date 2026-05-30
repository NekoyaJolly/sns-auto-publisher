from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.db.session import session_scope
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.media_process_service import MediaProcessService
from app.services.notify_service import NotifyService, ReceiveNotification
from app.services.validation_service import ValidationService
from app.storage.local_storage import LocalStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramMediaCandidate:
    file_id: str
    filename: str
    media_type: str
    mime_type: str


class TelegramBotMessenger:
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def send_message(self, chat_id: str, text: str) -> None:
        await self.bot.send_message(chat_id=chat_id, text=text)


class TelegramInput:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        storage: LocalStorage,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.storage = storage

    def run_polling(self) -> None:
        if not self.settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKENが設定されていません")

        from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

        application = ApplicationBuilder().token(self.settings.telegram_bot_token).build()
        application.add_handler(CommandHandler("start", self.handle_start))
        application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, self.handle_media))
        logger.info("Telegram Botのpollingを開始します")
        application.run_polling()

    async def handle_start(self, update: Any, context: Any) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        await context.bot.send_message(chat_id=chat_id, text="SNS投稿オーケストレーターを起動しています。画像または動画を送信してください。")

    async def handle_media(self, update: Any, context: Any) -> None:
        chat_id = self._chat_id(update)
        user_id = self._user_id(update)
        if chat_id is None:
            return

        messenger = TelegramBotMessenger(context.bot)
        notify_service = NotifyService(messenger)

        if not self.is_allowed_chat(chat_id):
            await notify_service.notify_rejected(chat_id, "許可されていないchat_idです")
            return

        candidate = self.extract_media_candidate(update)
        if candidate is None:
            await notify_service.notify_rejected(chat_id, "画像または動画のみ受信できます")
            return

        try:
            incoming_media = await self.download_media(context.bot, candidate)
            with session_scope(self.session_factory) as session:
                ingest_service = IngestService(session=session, storage=self.storage, settings=self.settings)
                result = ingest_service.ingest_telegram_media(
                    chat_id=chat_id,
                    user_id=user_id,
                    media_files=[incoming_media],
                )
                validation_results = ValidationService(session=session, settings=self.settings).validate_post_job(
                    result.post_job
                )
                if not all(validation_result.is_valid for validation_result in validation_results):
                    reason = "; ".join(
                        validation_result.reason or "検証に失敗しました" for validation_result in validation_results
                    )
                    await notify_service.notify_rejected(chat_id, reason)
                    return

                if any(media_asset.media_type == "image" for media_asset in result.media_assets):
                    MediaProcessService(session=session, storage=self.storage).process_post_job_images(result.post_job)

                post_job_id = result.post_job.id
                media_count = len(result.media_assets)
            await notify_service.notify_received(
                chat_id,
                ReceiveNotification(post_job_id=post_job_id, media_count=media_count),
            )
        except Exception as exc:
            logger.exception("Telegramメディア受信処理に失敗しました")
            await notify_service.notify_rejected(chat_id, str(exc))

    def is_allowed_chat(self, chat_id: str) -> bool:
        if not self.settings.telegram_allowed_chat_ids:
            return True
        return chat_id in self.settings.telegram_allowed_chat_ids

    def extract_media_candidate(self, update: Any) -> TelegramMediaCandidate | None:
        message = getattr(update, "message", None)
        if message is None:
            return None

        if getattr(message, "photo", None):
            photo = message.photo[-1]
            filename = f"{photo.file_unique_id}.jpg"
            return TelegramMediaCandidate(
                file_id=photo.file_id,
                filename=filename,
                media_type="image",
                mime_type="image/jpeg",
            )

        video = getattr(message, "video", None)
        if video is not None:
            filename = video.file_name or f"{video.file_unique_id}.mp4"
            return TelegramMediaCandidate(
                file_id=video.file_id,
                filename=filename,
                media_type="video",
                mime_type=video.mime_type or "video/mp4",
            )

        document = getattr(message, "document", None)
        if document is not None and self._supported_document_mime(document.mime_type):
            media_type = "image" if document.mime_type.startswith("image/") else "video"
            filename = document.file_name or f"{document.file_unique_id}"
            return TelegramMediaCandidate(
                file_id=document.file_id,
                filename=filename,
                media_type=media_type,
                mime_type=document.mime_type,
            )

        return None

    async def download_media(self, bot: Any, candidate: TelegramMediaCandidate) -> IncomingMediaFile:
        telegram_file = await bot.get_file(candidate.file_id)
        content = bytes(await telegram_file.download_as_bytearray())
        return IncomingMediaFile(
            filename=candidate.filename,
            content=content,
            media_type=candidate.media_type,
            mime_type=candidate.mime_type,
        )

    @staticmethod
    def _supported_document_mime(mime_type: str | None) -> bool:
        if mime_type is None:
            return False
        return mime_type.startswith("image/") or mime_type.startswith("video/")

    @staticmethod
    def _chat_id(update: Any) -> str | None:
        chat = getattr(update, "effective_chat", None)
        if chat is None:
            return None
        return str(chat.id)

    @staticmethod
    def _user_id(update: Any) -> str | None:
        user = getattr(update, "effective_user", None)
        if user is None:
            return None
        return str(user.id)
