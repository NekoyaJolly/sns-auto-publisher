from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.models import MediaAsset, MediaAssetStatus, PostJob, PostJobStatus
from app.db.repository import Repository
from app.utils.media_probe import probe_image
from app.utils.mime_detect import media_type_from_mime


@dataclass(frozen=True)
class MediaValidationResult:
    media_asset_id: int
    is_valid: bool
    reason: str | None = None


class ValidationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.repository = Repository(session)
        self.settings = settings

    def validate_post_job(self, post_job: PostJob) -> list[MediaValidationResult]:
        self.repository.update_post_job_status(post_job, PostJobStatus.VALIDATING)
        results = [self.validate_media_asset(media_asset) for media_asset in post_job.media_assets]
        if results and all(result.is_valid for result in results):
            self.repository.update_post_job_status(post_job, PostJobStatus.VALIDATED)
        else:
            reason = "; ".join(result.reason or "検証に失敗しました" for result in results if not result.is_valid)
            self.repository.update_post_job_status(post_job, PostJobStatus.FAILED, error_message=reason)
        return results

    def validate_media_asset(self, media_asset: MediaAsset) -> MediaValidationResult:
        path = Path(media_asset.original_path)
        if not path.exists():
            return self._reject(media_asset, "rawファイルが存在しません")

        expected_media_type = media_type_from_mime(media_asset.mime_type)
        if expected_media_type is None:
            return self._reject(media_asset, "画像または動画以外のMIME typeです")
        if media_asset.media_type != expected_media_type:
            return self._reject(media_asset, "media_typeとMIME typeが一致しません")

        max_size_mb = self._max_size_mb(media_asset.media_type)
        if media_asset.file_size > max_size_mb * 1024 * 1024:
            return self._reject(media_asset, f"ファイルサイズが上限{max_size_mb}MBを超えています")

        if media_asset.media_type == "image":
            return self._validate_image(media_asset, path)

        self.repository.update_media_asset_validation(
            media_asset,
            status=MediaAssetStatus.VALIDATED,
            error_message=None,
        )
        return MediaValidationResult(media_asset_id=media_asset.id, is_valid=True)

    def _validate_image(self, media_asset: MediaAsset, path: Path) -> MediaValidationResult:
        try:
            image_info = probe_image(path)
        except ValueError as exc:
            return self._fail(media_asset, str(exc))

        self.repository.update_media_asset_validation(
            media_asset,
            status=MediaAssetStatus.VALIDATED,
            width=image_info.width,
            height=image_info.height,
            error_message=None,
        )
        return MediaValidationResult(media_asset_id=media_asset.id, is_valid=True)

    def _max_size_mb(self, media_type: str) -> int:
        if media_type == "image":
            return self.settings.max_image_size_mb
        return self.settings.max_video_size_mb

    def _reject(self, media_asset: MediaAsset, reason: str) -> MediaValidationResult:
        self.repository.update_media_asset_validation(
            media_asset,
            status=MediaAssetStatus.REJECTED,
            error_message=reason,
        )
        return MediaValidationResult(media_asset_id=media_asset.id, is_valid=False, reason=reason)

    def _fail(self, media_asset: MediaAsset, reason: str) -> MediaValidationResult:
        self.repository.update_media_asset_validation(
            media_asset,
            status=MediaAssetStatus.FAILED,
            error_message=reason,
        )
        return MediaValidationResult(media_asset_id=media_asset.id, is_valid=False, reason=reason)
