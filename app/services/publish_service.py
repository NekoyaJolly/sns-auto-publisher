from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import PostJob, PostJobStatus
from app.db.repository import Repository
from app.publishers.x_publisher import XPublishResult, XPublisher, build_x_post_text

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    def publish(self, post_job: PostJob) -> XPublishResult:
        pass


@dataclass(frozen=True)
class PublishServiceResult:
    is_success: bool
    x_post_id: str | None = None
    error_message: str | None = None


class PublishService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        publisher: Publisher | None = None,
    ) -> None:
        self.repository = Repository(session)
        self.settings = settings
        self.publisher = publisher

    def publish_post_job(self, post_job: PostJob) -> PublishServiceResult:
        if post_job.status != PostJobStatus.PUBLISHING.value:
            raise ValueError("X投稿はpublishing状態のpost_jobのみ実行できます")

        request_payload = self._request_payload(post_job)
        try:
            publisher = self.publisher or XPublisher(self.settings)
            result = publisher.publish(post_job)
        except Exception as exc:
            logger.exception("X投稿に失敗しました")
            error_message = str(exc)
            self.repository.create_post_attempt(
                post_job_id=post_job.id,
                provider="x",
                request_payload_json=json.dumps(request_payload, ensure_ascii=False),
                response_payload_json=None,
                status="failed",
                error_message=error_message,
            )
            self.repository.update_post_job_status(post_job, PostJobStatus.FAILED, error_message=error_message)
            return PublishServiceResult(is_success=False, error_message=error_message)

        response_payload = {
            "x_post_id": result.x_post_id,
            "media_ids": result.media_ids,
        }
        self.repository.create_post_attempt(
            post_job_id=post_job.id,
            provider="x",
            request_payload_json=json.dumps(request_payload, ensure_ascii=False),
            response_payload_json=json.dumps(response_payload, ensure_ascii=False),
            status="succeeded",
        )
        self.repository.update_post_job_published(post_job, x_post_id=result.x_post_id)
        return PublishServiceResult(is_success=True, x_post_id=result.x_post_id)

    @staticmethod
    def _request_payload(post_job: PostJob) -> dict[str, object]:
        return {
            "text": build_x_post_text(post_job),
            "media_paths": [media_asset.processed_path for media_asset in post_job.media_assets],
            "mode": post_job.mode,
        }
