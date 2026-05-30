from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import (
    AppSetting,
    MediaAsset,
    MediaAssetStatus,
    PostAttempt,
    PostJob,
    PostJobStatus,
    PostingMode,
)


def _enum_value(value: str | PostingMode | PostJobStatus | MediaAssetStatus) -> str:
    return value.value if hasattr(value, "value") else str(value)


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_post_job(
        self,
        *,
        source_type: str,
        source_chat_id: str | None = None,
        source_user_id: str | None = None,
        mode: PostingMode | str = PostingMode.APPROVAL,
        status: PostJobStatus | str = PostJobStatus.RECEIVED,
    ) -> PostJob:
        post_job = PostJob(
            source_type=source_type,
            source_chat_id=source_chat_id,
            source_user_id=source_user_id,
            mode=_enum_value(mode),
            status=_enum_value(status),
        )
        self.session.add(post_job)
        self.session.flush()
        return post_job

    def create_media_asset(
        self,
        *,
        post_job_id: int,
        original_path: str,
        media_type: str,
        mime_type: str,
        file_hash: str,
        file_size: int,
        processed_path: str | None = None,
        thumbnail_path: str | None = None,
        width: int | None = None,
        height: int | None = None,
        duration_seconds: float | None = None,
        status: MediaAssetStatus | str = MediaAssetStatus.RECEIVED,
    ) -> MediaAsset:
        media_asset = MediaAsset(
            post_job_id=post_job_id,
            original_path=original_path,
            processed_path=processed_path,
            thumbnail_path=thumbnail_path,
            media_type=media_type,
            mime_type=mime_type,
            file_hash=file_hash,
            file_size=file_size,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            status=_enum_value(status),
        )
        self.session.add(media_asset)
        self.session.flush()
        return media_asset

    def create_post_attempt(
        self,
        *,
        post_job_id: int,
        provider: str,
        status: str,
        request_payload_json: str | None = None,
        response_payload_json: str | None = None,
        error_message: str | None = None,
    ) -> PostAttempt:
        post_attempt = PostAttempt(
            post_job_id=post_job_id,
            provider=provider,
            request_payload_json=request_payload_json,
            response_payload_json=response_payload_json,
            status=status,
            error_message=error_message,
        )
        self.session.add(post_attempt)
        self.session.flush()
        return post_attempt

    def get_post_job(self, post_job_id: int) -> PostJob | None:
        return self.session.get(PostJob, post_job_id)

    def get_media_asset(self, media_asset_id: int) -> MediaAsset | None:
        return self.session.get(MediaAsset, media_asset_id)

    def update_post_job_status(
        self,
        post_job: PostJob,
        status: PostJobStatus | str,
        *,
        error_message: str | None = None,
    ) -> PostJob:
        post_job.status = _enum_value(status)
        post_job.error_message = error_message
        self.session.flush()
        return post_job

    def update_media_asset_validation(
        self,
        media_asset: MediaAsset,
        *,
        status: MediaAssetStatus | str,
        width: int | None = None,
        height: int | None = None,
        duration_seconds: float | None = None,
        error_message: str | None = None,
    ) -> MediaAsset:
        media_asset.status = _enum_value(status)
        media_asset.width = width
        media_asset.height = height
        media_asset.duration_seconds = duration_seconds
        media_asset.error_message = error_message
        self.session.flush()
        return media_asset

    def update_media_asset_processed(
        self,
        media_asset: MediaAsset,
        *,
        processed_path: str,
        thumbnail_path: str,
        width: int,
        height: int,
        status: MediaAssetStatus | str = MediaAssetStatus.PROCESSED,
    ) -> MediaAsset:
        media_asset.processed_path = processed_path
        media_asset.thumbnail_path = thumbnail_path
        media_asset.width = width
        media_asset.height = height
        media_asset.status = _enum_value(status)
        media_asset.error_message = None
        self.session.flush()
        return media_asset

    def set_app_setting(self, key: str, value: str) -> AppSetting:
        setting = self.session.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=value)
            self.session.add(setting)
        else:
            setting.value = value
        self.session.flush()
        return setting
