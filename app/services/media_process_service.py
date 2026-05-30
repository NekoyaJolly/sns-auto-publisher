from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.db.models import MediaAsset, MediaAssetStatus, PostJob, PostJobStatus
from app.db.repository import Repository
from app.storage.local_storage import LocalStorage, StorageArea
from app.utils.ffmpeg_runner import FFmpegError, FFmpegRunner


class MediaProcessService:
    def __init__(
        self,
        session: Session,
        storage: LocalStorage,
        *,
        max_image_side: int = 2048,
        max_video_width: int = 1920,
        max_video_height: int = 1920,
        thumbnail_side: int = 512,
        ffmpeg_runner: FFmpegRunner | None = None,
    ) -> None:
        self.repository = Repository(session)
        self.storage = storage
        self.max_image_side = max_image_side
        self.max_video_width = max_video_width
        self.max_video_height = max_video_height
        self.thumbnail_side = thumbnail_side
        self.ffmpeg_runner = ffmpeg_runner or FFmpegRunner()

    def process_post_job_images(self, post_job: PostJob) -> list[MediaAsset]:
        return self.process_post_job_media(post_job)

    def process_post_job_media(self, post_job: PostJob) -> list[MediaAsset]:
        self.repository.update_post_job_status(post_job, PostJobStatus.PROCESSING)
        processed_assets: list[MediaAsset] = []

        for media_asset in post_job.media_assets:
            if media_asset.status != MediaAssetStatus.VALIDATED.value:
                continue
            if media_asset.media_type == "image":
                processed_assets.append(self.process_image_asset(media_asset))
            elif media_asset.media_type == "video":
                processed_assets.append(self.process_video_asset(media_asset))

        self.repository.update_post_job_status_from_media_assets(post_job)
        return processed_assets

    def process_image_asset(self, media_asset: MediaAsset) -> MediaAsset:
        if media_asset.status != MediaAssetStatus.VALIDATED.value:
            raise ValueError("画像処理はvalidated状態のmedia_assetのみ実行できます")

        source_path = Path(media_asset.original_path)
        processed_path = self.storage.unique_path(
            StorageArea.PROCESSED,
            media_asset.post_job_id,
            f"{source_path.stem}.jpg",
        )
        thumbnail_path = self.storage.unique_path(
            StorageArea.THUMBNAILS,
            media_asset.post_job_id,
            f"{source_path.stem}.jpg",
        )

        with Image.open(source_path) as image:
            normalized = self._normalize_image(image)
            processed_image = self._resize_to_fit(normalized, self.max_image_side)
            processed_image.save(processed_path, format="JPEG", quality=90, optimize=True)

            thumbnail_image = processed_image.copy()
            thumbnail_image.thumbnail((self.thumbnail_side, self.thumbnail_side), Image.Resampling.LANCZOS)
            thumbnail_image.save(thumbnail_path, format="JPEG", quality=85, optimize=True)

        return self.repository.update_media_asset_processed(
            media_asset,
            processed_path=self._storage_path(processed_path),
            thumbnail_path=self._storage_path(thumbnail_path),
            width=processed_image.width,
            height=processed_image.height,
        )

    def process_video_asset(self, media_asset: MediaAsset) -> MediaAsset:
        if media_asset.status != MediaAssetStatus.VALIDATED.value:
            raise ValueError("動画処理はvalidated状態のmedia_assetのみ実行できます")

        source_path = Path(media_asset.original_path)
        processed_path = self.storage.unique_path(
            StorageArea.PROCESSED,
            media_asset.post_job_id,
            f"{source_path.stem}.mp4",
        )
        thumbnail_path = self.storage.unique_path(
            StorageArea.THUMBNAILS,
            media_asset.post_job_id,
            f"{source_path.stem}.jpg",
        )

        try:
            self.ffmpeg_runner.convert_to_mp4(
                input_path=source_path,
                output_path=processed_path,
                max_width=self.max_video_width,
                max_height=self.max_video_height,
            )
            processed_info = self.ffmpeg_runner.probe_video(processed_path)
            self.ffmpeg_runner.create_thumbnail(input_path=processed_path, output_path=thumbnail_path)
        except FFmpegError as exc:
            return self.repository.mark_media_asset_failed(media_asset, str(exc))

        return self.repository.update_media_asset_processed(
            media_asset,
            processed_path=self._storage_path(processed_path),
            thumbnail_path=self._storage_path(thumbnail_path),
            width=processed_info.width,
            height=processed_info.height,
            duration_seconds=processed_info.duration_seconds,
        )

    def _normalize_image(self, image: Image.Image) -> Image.Image:
        transposed = ImageOps.exif_transpose(image)
        if transposed.mode in ("RGBA", "LA"):
            background = Image.new("RGB", transposed.size, (255, 255, 255))
            alpha = transposed.getchannel("A")
            background.paste(transposed.convert("RGB"), mask=alpha)
            return background
        return transposed.convert("RGB")

    @staticmethod
    def _resize_to_fit(image: Image.Image, max_side: int) -> Image.Image:
        resized = image.copy()
        resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return resized

    @staticmethod
    def _storage_path(path: Path) -> str:
        try:
            return path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return path.as_posix()
