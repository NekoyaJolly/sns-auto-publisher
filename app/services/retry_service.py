from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import MediaAssetStatus, PostJob, PostJobStatus
from app.db.repository import Repository
from app.services.publish_service import Publisher, PublishService


@dataclass(frozen=True)
class RetryResult:
    is_success: bool
    post_job: PostJob
    x_post_id: str | None = None
    error_message: str | None = None


class RetryService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        publisher: Publisher | None = None,
    ) -> None:
        self.repository = Repository(session)
        self.settings = settings
        self.publisher = publisher

    def retry_post_job(self, post_job_id: int) -> RetryResult:
        post_job = self.repository.require_post_job(post_job_id)
        validation_error = self._retry_validation_error(post_job)
        if validation_error is not None:
            return RetryResult(is_success=False, post_job=post_job, error_message=validation_error)

        self.repository.update_post_job_status(post_job, PostJobStatus.PUBLISHING)
        result = PublishService(
            session=self.repository.session,
            settings=self.settings,
            publisher=self.publisher,
        ).publish_post_job(post_job)
        return RetryResult(
            is_success=result.is_success,
            post_job=post_job,
            x_post_id=result.x_post_id,
            error_message=result.error_message,
        )

    @staticmethod
    def _retry_validation_error(post_job: PostJob) -> str | None:
        if post_job.status != PostJobStatus.FAILED.value:
            return "retryできるのはfailed状態のpost_jobのみです"
        if post_job.x_post_id:
            return "すでにx_post_idがあるためretryできません"
        if not post_job.caption:
            return "captionが未生成のためretryできません"
        if not post_job.media_assets:
            return "media_assetsが存在しないためretryできません"
        if any(media_asset.status != MediaAssetStatus.PROCESSED.value for media_asset in post_job.media_assets):
            return "未処理または失敗したmedia_assetがあるためretryできません"
        return None
