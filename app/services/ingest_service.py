from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import MediaAsset, PostJob, PostingMode
from app.db.repository import Repository
from app.storage.local_storage import LocalStorage, StorageArea
from app.utils.file_hash import sha256_file


@dataclass(frozen=True)
class IncomingMediaFile:
    filename: str
    content: bytes
    media_type: str
    mime_type: str


@dataclass(frozen=True)
class IngestResult:
    post_job: PostJob
    media_assets: list[MediaAsset]


class IngestService:
    def __init__(self, session: Session, storage: LocalStorage, settings: Settings) -> None:
        self.repository = Repository(session)
        self.storage = storage
        self.settings = settings

    def ingest_telegram_media(
        self,
        *,
        chat_id: str,
        user_id: str | None,
        media_files: list[IncomingMediaFile],
    ) -> IngestResult:
        if not media_files:
            raise ValueError("media_filesは1件以上必要です")

        post_job = self.repository.create_post_job(
            source_type="telegram",
            source_chat_id=chat_id,
            source_user_id=user_id,
            mode=self.settings.posting_mode,
        )
        media_assets = [
            self._save_and_register_media(post_job_id=post_job.id, media_file=media_file)
            for media_file in media_files
        ]
        return IngestResult(post_job=post_job, media_assets=media_assets)

    def _save_and_register_media(self, *, post_job_id: int, media_file: IncomingMediaFile) -> MediaAsset:
        saved_path = self.storage.save_bytes(
            StorageArea.RAW,
            post_job_id,
            media_file.filename,
            media_file.content,
        )
        return self.repository.create_media_asset(
            post_job_id=post_job_id,
            original_path=self._storage_path(saved_path),
            media_type=media_file.media_type,
            mime_type=media_file.mime_type,
            file_hash=sha256_file(saved_path),
            file_size=saved_path.stat().st_size,
        )

    def _storage_path(self, path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()
