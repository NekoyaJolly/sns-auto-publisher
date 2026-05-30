from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.db.models import MediaAsset, MediaAssetStatus, PostJob, PostJobStatus
from app.db.repository import Repository
from app.storage.local_storage import LocalStorage, StorageArea


class MediaProcessService:
    def __init__(
        self,
        session: Session,
        storage: LocalStorage,
        *,
        max_image_side: int = 2048,
        thumbnail_side: int = 512,
    ) -> None:
        self.repository = Repository(session)
        self.storage = storage
        self.max_image_side = max_image_side
        self.thumbnail_side = thumbnail_side

    def process_post_job_images(self, post_job: PostJob) -> list[MediaAsset]:
        self.repository.update_post_job_status(post_job, PostJobStatus.PROCESSING)
        processed_assets: list[MediaAsset] = []

        for media_asset in post_job.media_assets:
            if media_asset.media_type != "image":
                continue
            processed_assets.append(self.process_image_asset(media_asset))

        if processed_assets and all(asset.status == MediaAssetStatus.PROCESSED.value for asset in processed_assets):
            self.repository.update_post_job_status(post_job, PostJobStatus.PROCESSED)
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
