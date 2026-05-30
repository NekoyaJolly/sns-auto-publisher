from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import PostJob
from app.db.repository import Repository


class StatusService:
    def __init__(self, session: Session) -> None:
        self.repository = Repository(session)

    def build_status_text(self, post_job_id: int) -> str:
        post_job = self.repository.require_post_job(post_job_id)
        return build_post_job_status_text(post_job)


def build_post_job_status_text(post_job: PostJob) -> str:
    lines = [
        f"job_id={post_job.id}",
        f"mode={post_job.mode}",
        f"status={post_job.status}",
        f"media={len(post_job.media_assets)}",
    ]
    if post_job.x_post_id:
        lines.append(f"x_post_id={post_job.x_post_id}")
    if post_job.error_message:
        lines.append(f"error={post_job.error_message}")
    if post_job.media_assets:
        lines.append("media_status:")
        lines.extend(
            f"- id={media_asset.id} type={media_asset.media_type} status={media_asset.status}"
            for media_asset in post_job.media_assets
        )
    if post_job.post_attempts:
        latest_attempt = max(post_job.post_attempts, key=lambda post_attempt: post_attempt.id)
        lines.append(f"latest_attempt={latest_attempt.provider}:{latest_attempt.status}")
    return "\n".join(lines)
