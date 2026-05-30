from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.db.models import PostJob, PostJobStatus, PostingMode
from app.db.repository import Repository
from app.db.session import session_scope
from app.services.caption_service import CaptionGenerator, CaptionService
from app.services.ingest_service import IncomingMediaFile, IngestService
from app.services.media_process_service import MediaProcessService
from app.services.mode_service import ModeService, posting_mode_help_text
from app.services.notify_service import NotifyService, ReceiveNotification
from app.services.preview_service import PreviewService, build_preview_text
from app.services.publish_service import Publisher, PublishService
from app.services.retry_service import RetryService
from app.services.status_service import StatusService
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

    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


class TelegramInput:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        storage: LocalStorage,
        caption_generator: CaptionGenerator | None = None,
        publisher: Publisher | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.storage = storage
        self.caption_generator = caption_generator
        self.publisher = publisher

    def run_polling(self) -> None:
        if not self.settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKENが設定されていません")

        from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

        application = ApplicationBuilder().token(self.settings.telegram_bot_token).build()
        application.add_handler(CommandHandler("start", self.handle_start))
        application.add_handler(CommandHandler("mode", self.handle_mode_command))
        application.add_handler(CommandHandler("retry", self.handle_retry_command))
        application.add_handler(CommandHandler("status", self.handle_status_command))
        application.add_handler(CallbackQueryHandler(self.handle_preview_callback, pattern=r"^post:"))
        application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, self.handle_media))
        logger.info("Telegram Botのpollingを開始します")
        application.run_polling()

    async def handle_start(self, update: Any, context: Any) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        await context.bot.send_message(chat_id=chat_id, text="SNS投稿オーケストレーターを起動しています。画像または動画を送信してください。")

    async def handle_mode_command(self, update: Any, context: Any) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        if not self.is_allowed_chat(chat_id):
            await context.bot.send_message(chat_id=chat_id, text="許可されていないchat_idです")
            return

        args = [str(arg) for arg in getattr(context, "args", [])]
        with session_scope(self.session_factory) as session:
            mode_service = ModeService(session=session, settings=self.settings)
            if not args:
                await context.bot.send_message(chat_id=chat_id, text=posting_mode_help_text(mode_service.get_mode()))
                return
            try:
                posting_mode = mode_service.set_mode(args[0])
            except ValueError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="投稿モードは approval / auto / dry_run のいずれかを指定してください。",
                )
                return
        await context.bot.send_message(chat_id=chat_id, text=f"投稿モードを {posting_mode.value} に変更しました")

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
                current_mode = ModeService(session=session, settings=self.settings).get_mode()
                ingest_service = IngestService(session=session, storage=self.storage, settings=self.settings)
                result = ingest_service.ingest_telegram_media(
                    chat_id=chat_id,
                    user_id=user_id,
                    media_files=[incoming_media],
                    mode=current_mode,
                )
                if result.post_job.status in {PostJobStatus.FAILED.value, PostJobStatus.REJECTED.value}:
                    await notify_service.notify_rejected(chat_id, result.post_job.error_message or "受信処理に失敗しました")
                    return

                validation_results = ValidationService(session=session, settings=self.settings).validate_post_job(
                    result.post_job
                )
                if not all(validation_result.is_valid for validation_result in validation_results):
                    reason = "; ".join(
                        validation_result.reason or "検証に失敗しました" for validation_result in validation_results
                    )
                    await notify_service.notify_rejected(chat_id, reason)
                    return

                has_video = any(media_asset.media_type == "video" for media_asset in result.media_assets)
                MediaProcessService(session=session, storage=self.storage).process_post_job_media(result.post_job)
                if result.post_job.status in {PostJobStatus.FAILED.value, PostJobStatus.REJECTED.value}:
                    await notify_service.notify_rejected(chat_id, result.post_job.error_message or "メディア処理に失敗しました")
                    return

                CaptionService(
                    session=session,
                    settings=self.settings,
                    generator=self.caption_generator,
                ).caption_post_job(result.post_job)
                if result.post_job.status in {PostJobStatus.FAILED.value, PostJobStatus.REJECTED.value}:
                    await notify_service.notify_rejected(chat_id, result.post_job.error_message or "AI生成に失敗しました")
                    return

                post_job_id = result.post_job.id
                media_count = len(result.media_assets)
                detail = "動画処理完了 / AI生成完了" if has_video else "AI生成完了"
                if result.post_job.mode == PostingMode.APPROVAL.value:
                    await PreviewService(
                        session=session,
                        settings=self.settings,
                        messenger=messenger,
                        caption_generator=self.caption_generator,
                        publisher=self.publisher,
                    ).send_preview(chat_id, result.post_job)
                    detail = f"{detail} / プレビュー送信完了"
                elif result.post_job.mode == PostingMode.AUTO.value:
                    if not await self._handle_auto_mode(chat_id, result.post_job, messenger, session):
                        return
                    detail = f"{detail} / auto処理へ進行"
                elif result.post_job.mode == PostingMode.DRY_RUN.value:
                    await self._handle_dry_run_mode(chat_id, result.post_job, messenger, session)
                    detail = f"{detail} / dry_run確認送信完了"
            await notify_service.notify_received(
                chat_id,
                ReceiveNotification(post_job_id=post_job_id, media_count=media_count, detail=detail),
            )
        except Exception as exc:
            logger.exception("Telegramメディア受信処理に失敗しました")
            await notify_service.notify_rejected(chat_id, str(exc))

    async def _handle_auto_mode(self, chat_id: str, post_job: PostJob, messenger: TelegramBotMessenger, session: Session) -> bool:
        warnings = json.loads(post_job.ai_warnings_json or "[]")
        if warnings or not post_job.caption:
            Repository(session).update_post_job_status(
                post_job,
                PostJobStatus.REJECTED,
                error_message="auto投稿条件を満たしません",
            )
            await messenger.send_message(chat_id=chat_id, text="auto mode: 条件を満たさないため投稿を停止しました")
            return False
        Repository(session).update_post_job_status(post_job, PostJobStatus.PUBLISHING)
        result = PublishService(
            session=session,
            settings=self.settings,
            publisher=self.publisher,
        ).publish_post_job(post_job)
        if result.is_success:
            await NotifyService(messenger).notify_published(chat_id, post_job_id=post_job.id, x_post_id=result.x_post_id)
            return True
        await NotifyService(messenger).notify_failed(chat_id, post_job_id=post_job.id, reason=result.error_message)
        return False

    async def _handle_dry_run_mode(self, chat_id: str, post_job: PostJob, messenger: TelegramBotMessenger, session: Session) -> None:
        Repository(session).update_post_job_status(post_job, PostJobStatus.PREVIEW_SENT)
        await messenger.send_message(
            chat_id=chat_id,
            text=f"dry_run mode: Xへ投稿せず確認のみ行います。\n\n{build_preview_text(post_job)}",
        )

    async def handle_preview_callback(self, update: Any, context: Any) -> None:
        query = getattr(update, "callback_query", None)
        if query is None:
            return
        await query.answer()

        chat_id = self._chat_id(update)
        callback_data = getattr(query, "data", "")
        if chat_id is None:
            return

        messenger = TelegramBotMessenger(context.bot)
        try:
            with session_scope(self.session_factory) as session:
                await PreviewService(
                    session=session,
                    settings=self.settings,
                    messenger=messenger,
                    caption_generator=self.caption_generator,
                    publisher=self.publisher,
                ).handle_callback(chat_id, callback_data)
        except Exception as exc:
            logger.exception("Telegramプレビューcallback処理に失敗しました")
            await messenger.send_message(chat_id=chat_id, text=f"操作に失敗しました: {exc}")

    async def handle_retry_command(self, update: Any, context: Any) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        messenger = TelegramBotMessenger(context.bot)
        notify_service = NotifyService(messenger)
        if not self.is_allowed_chat(chat_id):
            await notify_service.notify_rejected(chat_id, "許可されていないchat_idです")
            return

        post_job_id = self._post_job_id_arg(context)
        if post_job_id is None:
            await messenger.send_message(chat_id=chat_id, text="使い方: /retry <job_id>")
            return

        try:
            with session_scope(self.session_factory) as session:
                result = RetryService(
                    session=session,
                    settings=self.settings,
                    publisher=self.publisher,
                ).retry_post_job(post_job_id)
                if result.is_success:
                    await notify_service.notify_published(chat_id, post_job_id=post_job_id, x_post_id=result.x_post_id)
                    return
                await notify_service.notify_failed(chat_id, post_job_id=post_job_id, reason=result.error_message)
        except Exception as exc:
            logger.exception("Telegram retry処理に失敗しました")
            await notify_service.notify_failed(chat_id, post_job_id=post_job_id, reason=str(exc))

    async def handle_status_command(self, update: Any, context: Any) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        messenger = TelegramBotMessenger(context.bot)
        notify_service = NotifyService(messenger)
        if not self.is_allowed_chat(chat_id):
            await notify_service.notify_rejected(chat_id, "許可されていないchat_idです")
            return

        post_job_id = self._post_job_id_arg(context)
        if post_job_id is None:
            await messenger.send_message(chat_id=chat_id, text="使い方: /status <job_id>")
            return

        try:
            with session_scope(self.session_factory) as session:
                text = StatusService(session).build_status_text(post_job_id)
            await messenger.send_message(chat_id=chat_id, text=text)
        except Exception as exc:
            logger.exception("Telegram status処理に失敗しました")
            await messenger.send_message(chat_id=chat_id, text=f"状態確認に失敗しました: {exc}")

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
    def _post_job_id_arg(context: Any) -> int | None:
        args = [str(arg) for arg in getattr(context, "args", [])]
        if len(args) != 1:
            return None
        try:
            return int(args[0])
        except ValueError:
            return None

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
